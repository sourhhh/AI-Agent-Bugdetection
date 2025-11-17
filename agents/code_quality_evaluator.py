import json
import os
import difflib
import ast
import shutil
import subprocess
import html
from datetime import datetime
from typing import List, Dict, Any, Optional


class CodeQualityEvaluator:
    """针对已成功修复的样本做代码质量评估，并输出 HTML 可视化报告。

    评估指标（示例实现，便于本地扩展）：
    - 语法检查（compile）
    - AST 结构相似度（函数/类名重合度）
    - Linter 得分（尝试 flake8/pylint）
    - 代码规模/复杂度：行数、函数数、类数、平均函数长度
    - 改动大小（diff changed），改动越小越好

    输出：一个聚焦于 `success==True` 样本的 HTML 报告，包含每个样本的指标与综合质量分。
    """

    def __init__(self, repair_report_path: str):
        self.report_path = repair_report_path
        self.results: List[Dict[str, Any]] = []

    def load_report(self):
        if not os.path.exists(self.report_path):
            raise FileNotFoundError(self.report_path)
        with open(self.report_path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        detailed = data.get('detailed_results') or []
        self.results = detailed

    def try_load_file(self, path: str) -> Optional[str]:
        try:
            if path and os.path.exists(path):
                with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
                    return fh.read()
        except Exception:
            return None
        return None

    def _clean_snippet(self, s: str) -> str:
        """Remove line-number prefixes like '>>> L  1:' or '    L  3:' from snippets."""
        import re
        if not s:
            return s
        lines = []
        for ln in s.splitlines():
            # remove common prefix patterns used in our reports
            cleaned = re.sub(r'^\s*(?:>>>\s*)?L\s*\d+:\s*', '', ln)
            lines.append(cleaned)
        return '\n'.join(lines)

    def _run_linter_score(self, code: str) -> float:
        """简单封装：尝试 flake8/pylint，返回 0..1。若不可用返回 0.5"""
        tmp = None
        try:
            tmp_dir = os.path.join(os.getcwd(), 'tmp_qe')
            os.makedirs(tmp_dir, exist_ok=True)
            tmp = os.path.join(tmp_dir, 'tmp_qe.py')
            with open(tmp, 'w', encoding='utf-8') as fh:
                fh.write(code)

            flake = shutil.which('flake8')
            if flake:
                proc = subprocess.run([flake, '--format=default', tmp], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=20)
                out = proc.stdout or proc.stderr or ''
                issues = len([l for l in out.splitlines() if l.strip()])
                score = max(0.0, 1.0 - issues / 50.0)
                return score

            pyl = shutil.which('pylint')
            if pyl:
                proc = subprocess.run([pyl, '--score=no', tmp], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
                out = proc.stdout or proc.stderr or ''
                issues = len([l for l in out.splitlines() if ': ' in l])
                score = max(0.0, 1.0 - issues / 100.0)
                return score

            return 0.5
        except Exception:
            return 0.5
        finally:
            try:
                if tmp and os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass

    def _ast_metrics(self, code: str) -> Dict[str, int]:
        try:
            tree = ast.parse(code)
            funcs = 0
            classes = 0
            func_lens = []
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    funcs += 1
                    start = getattr(node, 'lineno', None)
                    end = getattr(node, 'end_lineno', None)
                    if start and end:
                        func_lens.append(max(0, end - start + 1))
                elif isinstance(node, ast.ClassDef):
                    classes += 1
            avg_fun = (sum(func_lens) / len(func_lens)) if func_lens else 0
            return {'funcs': funcs, 'classes': classes, 'avg_func_len': int(avg_fun)}
        except Exception:
            return {'funcs': 0, 'classes': 0, 'avg_func_len': 0}

    def _ast_similarity(self, a: str, b: str) -> float:
        # 以函数/类名集合重合度为相似度指标
        try:
            ta = ast.parse(a)
            tb = ast.parse(b)
            def names(t):
                fs=set(); cs=set()
                for n in ast.walk(t):
                    if isinstance(n, ast.FunctionDef): fs.add(n.name)
                    if isinstance(n, ast.ClassDef): cs.add(n.name)
                return fs, cs
            fa, ca = names(ta)
            fb, cb = names(tb)
            if not (fa or ca):
                return 0.5 if (fb or cb) else 1.0
            f_overlap = len(fa & fb) / max(1, len(fa | fb))
            c_overlap = len(ca & cb) / max(1, len(ca | cb))
            return 0.5 * f_overlap + 0.5 * c_overlap
        except Exception:
            return 0.5

    def compute_metrics_for_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        # 仅在 success==True 时计算
        orig = item.get('original_code_snippet','') or ''
        fixed = item.get('fixed_code_snippet','') or ''
        # 如果 snippet 不存在或为片段，优先尝试加载磁盘上保存的 fixed_<basename> 文件
        file_path = item.get('file_path') or ''
        working_fixed = ''
        working_orig = orig
        if file_path:
            base = os.path.basename(file_path)
            cand = os.path.join(os.path.dirname(file_path), f'fixed_{base}')
            loaded = self.try_load_file(cand)
            if loaded:
                working_fixed = loaded
            else:
                # if we have a snippet in JSON, clean it
                if fixed:
                    working_fixed = self._clean_snippet(fixed)
        else:
            if fixed:
                working_fixed = self._clean_snippet(fixed)

        if not working_orig and file_path:
            loaded_orig = self.try_load_file(file_path)
            if loaded_orig:
                working_orig = loaded_orig
        # metrics
        metrics = {}
        metrics['loc_fixed'] = len(working_fixed.splitlines()) if working_fixed else 0
        astm = self._ast_metrics(working_fixed) if working_fixed else {'funcs':0,'classes':0,'avg_func_len':0}
        metrics.update(astm)
        # syntax
        try:
            syntax_ok = False
            metrics['syntax_error_msg'] = ''
            if working_fixed:
                compile(working_fixed, '<string>', 'exec')
                syntax_ok = True
            metrics['syntax_ok'] = bool(syntax_ok)
        except Exception:
            import traceback
            metrics['syntax_ok'] = False
            metrics['syntax_error_msg'] = str(traceback.format_exc())

        # linter
        metrics['linter_score'] = self._run_linter_score(working_fixed) if working_fixed else 0.0

        # ast similarity
        metrics['ast_similarity'] = self._ast_similarity(working_orig or '', working_fixed or '') if (working_orig and working_fixed) else 0.5

        # store the cleaned/loaded texts for HTML display
        item['_q_orig_for_eval'] = working_orig
        item['_q_fixed_for_eval'] = working_fixed

        # diff changed (if included by evaluator)
        ds = item.get('_diff_stats') or {}
        changed = ds.get('changed', 0)
        metrics['changed'] = changed
        metrics['small_change_score'] = max(0.0, 1.0 - changed / max(1, changed + 10))

        # composite quality score (0..1)
        syntax_score = 1.0 if metrics.get('syntax_ok') else 0.0
        score = 0.3 * syntax_score + 0.3 * metrics.get('linter_score', 0.5) + 0.2 * metrics.get('ast_similarity',0.5) + 0.2 * metrics.get('small_change_score',0.5)
        metrics['quality_score'] = max(0.0, min(1.0, score))
        return metrics

    def evaluate(self):
        self.load_report()
        # annotate items with metrics for successful repairs only
        for item in self.results:
            if item.get('success'):
                item['_q_metrics'] = self.compute_metrics_for_item(item)

    def generate_html(self, out_path: str):
        self.evaluate()
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        succ_items = [it for it in self.results if it.get('success')]

        html_parts: List[str] = []
        html_parts.append('<!doctype html>')
        html_parts.append('<html><head><meta charset="utf-8"><title>代码质量评估报告</title>')
        html_parts.append('<style>')
        html_parts.append('body{font-family:Inter,Segoe UI,Arial,sans-serif;background:#f4f6f8;color:#071130;padding:18px;margin:0}')
        html_parts.append('.wrap{max-width:1100px;margin:0 auto}')
        html_parts.append('.meta{color:#475569;margin-bottom:10px}')
        html_parts.append('table{width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden}')
        html_parts.append('th,td{padding:8px 10px;border-bottom:1px solid #eef2f7;text-align:left}')
        html_parts.append('th{background:#fbfdff;font-weight:600}')
        html_parts.append('.code-box{background:#fff;border:1px solid #e6eef6;padding:10px;border-radius:6px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px;overflow:auto}')
        html_parts.append('.muted{color:#64748b} .score{font-weight:700}')
        # diff styles
        html_parts.append('.diff-container{border:1px solid #e6eef6;border-radius:6px;overflow:auto;margin-top:8px}')
        html_parts.append('.diff-line{display:flex;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px;margin:0}')
        html_parts.append('.diff-gutter{width:36px;padding:6px 8px;text-align:right;color:#334155;flex:0 0 36px;border-right:1px solid rgba(15,23,42,0.04)}')
        html_parts.append('.diff-content{flex:1;padding:6px 8px;white-space:pre;overflow:auto}')
        html_parts.append('.diff-line.added .diff-gutter, .diff-line.added .diff-content{background:#ecfdf5;color:#065f46}')
        html_parts.append('.diff-line.removed .diff-gutter, .diff-line.removed .diff-content{background:#fff1f2;color:#7f1d1d}')
        html_parts.append('.diff-line.context .diff-gutter, .diff-line.context .diff-content{background:#fbfdff;color:#334155}')
        html_parts.append('.diff-line.hunk .diff-gutter, .diff-line.hunk .diff-content{background:#eef2ff;color:#0f172a;font-weight:600}')
        html_parts.append('.diff-line.file .diff-gutter, .diff-line.file .diff-content{background:#f8fafc;color:#0f172a;font-weight:700}')
        html_parts.append('</style>')
        html_parts.append('</head><body><div class="wrap">')
        html_parts.append(f'<h1>代码质量评估报告（仅成功修复样本）</h1>')
        html_parts.append(f'<div class="meta">生成时间: {timestamp} &nbsp; | &nbsp; 成功样本数: {len(succ_items)}</div>')

        # Summary aggregates
        if succ_items:
            avg_score = sum((it.get('_q_metrics',{}).get('quality_score',0) for it in succ_items))/len(succ_items)
        else:
            avg_score = 0.0
        html_parts.append(f'<div class="meta">整体平均质量分: <span class="score">{avg_score:.2%}</span></div>')

        # Table of items
        html_parts.append('<table>')
        html_parts.append('<tr><th>#</th><th>file</th><th>语言</th><th>质量分</th><th>语法</th><th>linter</th><th>AST_sim</th><th>changed</th></tr>')
        for i, it in enumerate(succ_items):
            m = it.get('_q_metrics', {})
            fp = it.get('file_path') or it.get('file', '') or 'n/a'
            lang = it.get('language','unknown')
            qs = m.get('quality_score', 0.0)
            syntax = '是' if m.get('syntax_ok') else '否'
            lscore = m.get('linter_score',0.0)
            asim = m.get('ast_similarity',0.0)
            changed = m.get('changed',0)
            html_parts.append(f'<tr><td>{i+1}</td><td>{html.escape(str(fp))}</td><td>{lang}</td><td>{qs:.2%}</td><td>{syntax}</td><td>{lscore:.2%}</td><td>{asim:.2%}</td><td>{changed}</td></tr>')
        html_parts.append('</table>')

        # Per-item detail blocks
        for i, it in enumerate(succ_items):
            m = it.get('_q_metrics', {})
            fp = it.get('file_path') or ''
            html_parts.append(f'<h3 id="item_{i}">{i+1}. {html.escape(str(fp))}</h3>')
            html_parts.append('<div class="meta">')
            html_parts.append(f'质量分: <span class="score">{m.get("quality_score",0.0):.2%}</span> &nbsp; | &nbsp; 语法: {"是" if m.get("syntax_ok") else "否"} &nbsp; | &nbsp; linter: {m.get("linter_score",0.0):.2%} &nbsp; | &nbsp; AST_sim: {m.get("ast_similarity",0.0):.2%}</div>')
            # use cleaned/loaded texts when available (fall back to raw snippets)
            working_orig = it.get('_q_orig_for_eval') or it.get('original_code_snippet','') or ''
            working_fixed = it.get('_q_fixed_for_eval') or it.get('fixed_code_snippet','') or ''
            # if syntax failed, include the error message for inspection
            if not m.get('syntax_ok') and m.get('syntax_error_msg'):
                err = html.escape(m.get('syntax_error_msg') or '')
                html_parts.append(f'<div style="color:#b91c1c;margin-bottom:8px"><b>SyntaxError / 语法错误:</b><pre style="white-space:pre-wrap;margin:6px 0">{err}</pre></div>')
            orig = html.escape(working_orig or '')
            fixed = html.escape(working_fixed or '')
            html_parts.append('<div><b>原始代码（如可用）</b></div>')
            html_parts.append(f'<div class="code-box"><pre style="margin:0">{orig or "(原文不可用)"}</pre></div>')
            html_parts.append('<div><b>修复后代码</b></div>')
            html_parts.append(f'<div class="code-box"><pre style="margin:0">{fixed or "(修复内容不可用)"}</pre></div>')
            # diff using cleaned/loaded texts so differences are meaningful
            dlines = list(difflib.unified_diff((working_orig or '').splitlines(), (working_fixed or '').splitlines(), lineterm=''))
            if dlines:
                html_parts.append('<div><b>统一 diff</b></div>')
                html_parts.append('<div class="diff-container">')
                for ln in dlines:
                    # file headers
                    if ln.startswith('+++') or ln.startswith('---'):
                        html_parts.append(f'<div class="diff-line file"><div class="diff-gutter"></div><div class="diff-content">{html.escape(ln)}</div></div>')
                        continue
                    # hunk header
                    if ln.startswith('@@'):
                        html_parts.append(f'<div class="diff-line hunk"><div class="diff-gutter"></div><div class="diff-content">{html.escape(ln)}</div></div>')
                        continue
                    # added line
                    if ln.startswith('+'):
                        content = html.escape(ln[1:])
                        html_parts.append(f'<div class="diff-line added"><div class="diff-gutter">+</div><div class="diff-content">{content}</div></div>')
                        continue
                    # removed line
                    if ln.startswith('-'):
                        content = html.escape(ln[1:])
                        html_parts.append(f'<div class="diff-line removed"><div class="diff-gutter">-</div><div class="diff-content">{content}</div></div>')
                        continue
                    # context line (starts with space) or other
                    if ln.startswith(' '):
                        content = html.escape(ln[1:])
                        html_parts.append(f'<div class="diff-line context"><div class="diff-gutter">&nbsp;</div><div class="diff-content">{content}</div></div>')
                    else:
                        html_parts.append(f'<div class="diff-line context"><div class="diff-gutter"></div><div class="diff-content">{html.escape(ln)}</div></div>')
                html_parts.append('</div>')
            else:
                html_parts.append('<div class="muted">(无差异可显示)</div>')

        html_parts.append('</div></body></html>')

        # write
        out_dir = os.path.dirname(out_path) or '.'
        os.makedirs(out_dir, exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(html_parts))

        return out_path
