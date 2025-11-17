#!/usr/bin/env python3
import os
import sys
import json
import glob
import time
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agentcode.schemas.project_context import ProjectContext

# detectors
from agents.defect_detector import DefectDetector
from agents.defect_detector_java import DefectDetectorJava
from agents.defect_detector_qt import DefectDetectorQt

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def find_input_analysis_file() -> str:
    idir = os.path.join(os.path.dirname(__file__), 'input_data')
    if not os.path.isdir(idir):
        raise FileNotFoundError(f"input_data 目录不存在: {idir}")
    # 优先从 run_analysis.py 中读取被分析的 project_path，以确定项目名并匹配对应的 input_data 文件
    run_analysis_path = os.path.join(os.path.dirname(__file__), 'run_analysis.py')
    project_name = None
    try:
        if os.path.exists(run_analysis_path):
            with open(run_analysis_path, 'r', encoding='utf-8') as rf:
                # 逐行查找，忽略注释行，优先使用第一个非注释的 assignment
                import re
                for line in rf:
                    stripped = line.lstrip()
                    if not stripped or stripped.startswith('#'):
                        continue
                    m = re.search(r"project_path\s*=\s*[rR]?[\"]?([^\"\n']+)[\"]?", stripped)
                    if m:
                        proj_path = m.group(1).strip()
                        project_name = os.path.basename(proj_path.rstrip('/\\'))
                        break
    except Exception:
        project_name = None

    # Prefer explicit common names or the one inferred from run_analysis.py
    candidates = []
    if project_name:
        candidates.append(os.path.join(idir, f"{project_name}_analysis.json"))
    candidates.extend([
        os.path.join(idir, 'defects4j_analysis.json'),
        os.path.join(idir, 'requests_cache_analysis.json'),
        os.path.join(idir, 'qt_project_analysis.json')
    ])
    for c in candidates:
        if os.path.exists(c):
            return c
    # otherwise pick the newest json file
    files = glob.glob(os.path.join(idir, '*_analysis.json'))
    if not files:
        # fallback to any json
        files = glob.glob(os.path.join(idir, '*.json'))
    if not files:
        raise FileNotFoundError('未找到 input_data 下的分析 JSON 文件')
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return files[0]


def ensure_abs_paths(project_context: ProjectContext):
    root = project_context.project_root
    def abs_list(lst):
        out = []
        for p in lst or []:
            if not p:
                continue
            if os.path.isabs(p):
                out.append(os.path.normpath(p))
            else:
                out.append(os.path.normpath(os.path.join(root, p)))
        return out

    project_context.python_files = abs_list(getattr(project_context, 'python_files', []))
    project_context.java_files = abs_list(getattr(project_context, 'java_files', []))
    project_context.qt_files = abs_list(getattr(project_context, 'qt_files', []))
    project_context.c_files = abs_list(getattr(project_context, 'c_files', []))
    project_context.cpp_files = abs_list(getattr(project_context, 'cpp_files', []))


def infer_files_from_raw(raw_modules: dict, ext: str, project_root: str):
    res = []
    for fp in raw_modules.keys():
        if fp.lower().endswith(ext):
            if os.path.isabs(fp):
                res.append(os.path.normpath(fp))
            else:
                res.append(os.path.normpath(os.path.join(project_root, fp)))
    return res


def run():
    input_file = find_input_analysis_file()
    logging.info(f'使用分析输入文件: {input_file}')
    with open(input_file, 'r', encoding='utf-8') as f:
        a = json.load(f)

    project_context_data = a.get('project_context')
    raw_analysis = a.get('raw_analysis', {}) or {}

    if not project_context_data:
        raise ValueError('分析文件缺少 project_context 字段')

    # Create ProjectContext (from_json is tolerant)
    if isinstance(project_context_data, dict):
        pc = ProjectContext.from_json(project_context_data)
    else:
        pc = ProjectContext.from_json(project_context_data)

    # Ensure project_root exists
    proj_root = getattr(pc, 'project_root', '.')
    if not proj_root:
        proj_root = os.getcwd()
    pc.project_root = proj_root

    # If language lists missing, try infer from raw_analysis
    if not getattr(pc, 'java_files', []):
        pc.java_files = infer_files_from_raw(raw_analysis.get('modules', {}), '.java', pc.project_root)
    if not getattr(pc, 'cpp_files', []) and not getattr(pc, 'c_files', []):
        # infer from common C/C++ extensions
        modules = raw_analysis.get('modules', {})
        cpp_candidates = []
        for ext in ('.cpp', '.cc', '.cxx', '.c', '.h', '.hpp'):
            cpp_candidates.extend(infer_files_from_raw(modules, ext, pc.project_root))
        pc.cpp_files = cpp_candidates
    if not getattr(pc, 'python_files', []):
        pc.python_files = infer_files_from_raw(raw_analysis.get('modules', {}), '.py', pc.project_root)

    # Normalize to absolute paths
    ensure_abs_paths(pc)

    project_name = os.path.basename(pc.project_root.rstrip('/\\')) or 'project'

    # Prepare output container
    per_lang_reports = {'python': None, 'java': None, 'qt': None}

    # Run Python detector if any python files
    try:
        if getattr(pc, 'python_files', []):
            logging.info(f'检测到 Python 文件: {len(pc.python_files)}，启动 Python 检测器')
            det = DefectDetector()
            rep_json = det.detect(pc.to_json())
            per_lang_reports['python'] = json.loads(rep_json)
            logging.info('Python 检测完成')
    except Exception as e:
        logging.exception('Python 检测失败')

    # Run Java detector
    try:
        if getattr(pc, 'java_files', []):
            logging.info(f'检测到 Java 文件: {len(pc.java_files)}，启动 Java 检测器')
            detj = DefectDetectorJava()
            rep_json = detj.detect(pc.to_json())
            per_lang_reports['java'] = json.loads(rep_json)
            logging.info('Java 检测完成')
    except Exception as e:
        logging.exception('Java 检测失败')

    # Run Qt/C++ detector
    try:
        if getattr(pc, 'cpp_files', []) or getattr(pc, 'qt_files', []):
            count = len(getattr(pc, 'cpp_files', [])) + len(getattr(pc, 'qt_files', []))
            logging.info(f'检测到 C++/Qt 文件: {count}，启动 Qt/C++ 检测器')
            detq = DefectDetectorQt()
            rep_json = detq.detect(pc.to_json())
            per_lang_reports['qt'] = json.loads(rep_json)
            logging.info('C++/Qt 检测完成')
    except Exception:
        logging.exception('C++/Qt 检测失败')

    # Merge reports: concatenate files lists and sum summaries
    combined_files = []
    combined_summary = {}
    for lang, report in per_lang_reports.items():
        if not report:
            continue
        files = report.get('files', [])
        combined_files.extend(files)
        summary = report.get('summary', {}) or {}
        for k, v in summary.items():
            try:
                combined_summary[k] = combined_summary.get(k, 0) + int(v)
            except Exception:
                # non-int summary values: keep as list
                combined_summary[k] = summary[k]

    final = {
        'project_name': project_name,
        'project_root': pc.project_root,
        'generated_at': int(time.time()),
        'reports': per_lang_reports,
        'files': combined_files,
        'summary': combined_summary
    }

    out_dir = os.path.join(os.path.dirname(__file__), 'output')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f'{project_name}_defect_report.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(final, f, indent=2, ensure_ascii=False)

    logging.info(f'合并缺陷报告已生成: {out_path}')
    return out_path


if __name__ == '__main__':
    try:
        run()
    except Exception as e:
        logging.exception('运行失败')
        sys.exit(1)
