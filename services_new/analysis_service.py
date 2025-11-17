"""
代码分析服务 - 封装代码缺陷分析逻辑（AI优先，规则兜底）
"""
import logging
import json
import os
from typing import Dict, Any, List

import requests

from agents.decision_manager import DecisionManagerAgent
from schemas.defect_report import DefectReport, FileDefects, Defect

logger = logging.getLogger(__name__)


class AnalysisService:
    """代码分析服务类"""

    def __init__(self):
        self.decision_manager = DecisionManagerAgent()

    def analyze_code(self, code: str, file_path: str = "main.py") -> Dict[str, Any]:
        """
        分析代码缺陷 - AI优先，失败回退规则检测；并生成修复计划
        """
        logger.info(f"开始分析代码: {len(code)}字符, 文件: {file_path}")

        # 生成缺陷报告（AI优先）
        defect_report = self._generate_defect_report(code, file_path)

        # 使用DecisionManager分析缺陷并生成修复计划
        defect_report_json = defect_report.to_json()
        repair_plan_json = self.decision_manager.analyze(defect_report_json)

        # 解析修复计划
        from schemas.repair_plan import RepairPlan
        repair_plan = RepairPlan.from_json(repair_plan_json)

        return {
            "defects": [self._defect_to_dict(defect) for defect in defect_report.files[0].defects],
            "defect_count": len(defect_report.files[0].defects),
            "repair_tasks": len(repair_plan.tasks),
            "summary": {
                "security": len([d for d in defect_report.files[0].defects if d.type == "security"]),
                "syntax": len([d for d in defect_report.files[0].defects if d.type == "syntax"]),
                "logic": len([d for d in defect_report.files[0].defects if d.type == "logic"])
            },
            "repair_plan": repair_plan_json
        }

    def _generate_defect_report(self, code: str, file_path: str) -> DefectReport:
        """生成缺陷报告 - AI优先，失败回退规则检测"""
        defects = self._detect_defects_ai_first(code)

        file_defects = FileDefects(
            file_path=file_path,
            defects=defects
        )

        defect_report = DefectReport(
            files=[file_defects],
            summary={"total_defects": len(defects)}
        )

        return defect_report

    def _detect_defects_ai_first(self, code: str) -> List[Defect]:
        """优先使用DeepSeek进行缺陷检测，失败则回退规则检测"""
        ai_key = os.getenv("DEEPSEEK_API_KEY", "")
        if ai_key:
            try:
                defects = self._detect_defects_with_ai(code, ai_key)
                if defects:
                    return defects
            except Exception as e:
                logger.warning(f"AI缺陷检测失败，回退规则检测: {e}")

        return self._detect_defects_rule_based(code)

    def _detect_defects_with_ai(self, code: str, api_key: str) -> List[Defect]:
        """调用DeepSeek进行代码缺陷检测，返回规范化后的Defect列表"""
        api_url = "https://api.deepseek.com/chat/completions"

        prompt = (
            "你是代码缺陷检测专家。请分析以下Python代码，输出JSON数组，每个元素含有键: "
            "type(在['syntax','security','logic','performance','code_smell']), "
            "message(简洁中文描述), line_number(从1开始的整数), "
            "severity(在['CRITICAL','HIGH','MEDIUM','LOW']), confidence(0-1之间的小数)。\n\n"
            "代码如下：\n```python\n" + code[:6000] + "\n```\n\n"
            "只返回JSON数组，不要任何解释。"
        )

        data = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 1200,
            "stream": False
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        response = requests.post(api_url, headers=headers, json=data, timeout=(10, 40))
        if response.status_code != 200:
            logger.warning(f"DeepSeek分析失败: {response.status_code} {response.text[:200]}")
            return []

        content = response.json()["choices"][0]["message"]["content"].strip()

        # 提取JSON
        text = content
        if "```" in text:
            try:
                import re
                matches = re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL)
                if matches:
                    text = matches[-1].strip()
            except Exception:
                pass

        try:
            parsed = json.loads(text)
            if not isinstance(parsed, list):
                logger.warning("AI返回非数组，忽略")
                return []
        except Exception:
            logger.warning("AI返回解析JSON失败，忽略")
            return []

        valid_types = {"syntax", "security", "logic", "performance", "code_smell"}
        valid_severity = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}

        defects: List[Defect] = []
        for item in parsed:
            try:
                t = str(item.get("type", "")).lower()
                if t not in valid_types:
                    continue
                msg = str(item.get("message", "")).strip() or "检测到问题"
                ln = int(item.get("line_number", 1))
                sev = str(item.get("severity", "MEDIUM")).upper()
                if sev not in valid_severity:
                    sev = "MEDIUM"
                conf = float(item.get("confidence", 0.7))

                defects.append(Defect(
                    type=t, message=msg, line_number=max(1, ln), severity=sev, tool="llm", confidence=conf
                ))
            except Exception:
                continue

        return defects

    def _detect_defects_rule_based(self, code: str) -> List[Defect]:
        """规则检测兜底实现"""
        defects: List[Defect] = []
        lines = code.split('\n')

        for i, line in enumerate(lines, 1):
            line_lower = line.lower()

            if 'eval(' in line and 'ast.literal_eval' not in line:
                defects.append(Defect(
                    type="security", message="不安全的eval函数使用，可能导致代码注入", line_number=i,
                    severity="HIGH", tool="rule", confidence=0.9
                ))

            if 'import pickle' in line and '警告' not in line and 'warning' not in line_lower:
                defects.append(Defect(
                    type="security", message="不安全的pickle反序列化，可能存在安全风险", line_number=i,
                    severity="HIGH", tool="rule", confidence=0.8
                ))

            if any(keyword in line_lower for keyword in ['password', 'secret', 'key', 'token']) and '=' in line and (
                    '"' in line or "'" in line):
                defects.append(Defect(
                    type="security", message="检测到硬编码的密码或密钥", line_number=i,
                    severity="MEDIUM", tool="rule", confidence=0.7
                ))

            if any(keyword in line_lower for keyword in ['select', 'insert', 'update', 'delete']) and (
                    '%' in line or 'f"' in line or 'f\'' in line):
                defects.append(Defect(
                    type="security", message="可能的SQL注入漏洞，使用了字符串格式化", line_number=i,
                    severity="HIGH", tool="rule", confidence=0.8
                ))

            if any(cmd in line for cmd in ['os.popen', 'os.system', 'subprocess.call']):
                defects.append(Defect(
                    type="security", message="不安全的命令执行，可能存在命令注入风险", line_number=i,
                    severity="HIGH", tool="rule", confidence=0.8
                ))

            if 'prinnt' in line_lower:
                defects.append(Defect(
                    type="syntax", message="可能的拼写错误: 'prinnt' -> 'print'", line_number=i,
                    severity="MEDIUM", tool="rule", confidence=0.8
                ))

            if line_lower.strip() and not line_lower.startswith(' ') and not line_lower.startswith('\t') and any(
                    keyword in line_lower for keyword in ['def ', 'class ', 'if ', 'for ', 'while ']) and not line.endswith(':'):
                defects.append(Defect(
                    type="syntax", message="可能的缩进错误或缺少冒号", line_number=i,
                    severity="MEDIUM", tool="rule", confidence=0.6
                ))

            if '= None' in line and 'if' in line_lower and '==' not in line_lower and 'is' not in line_lower:
                defects.append(Defect(
                    type="logic", message="条件语句中使用了赋值操作符=而不是比较操作符==或is", line_number=i,
                    severity="HIGH", tool="rule", confidence=0.7
                ))

            if '/' in line and any(var in line for var in ['0', 'zero']):
                defects.append(Defect(
                    type="logic", message="可能的除零错误", line_number=i,
                    severity="HIGH", tool="rule", confidence=0.6
                ))

            if any(method in line for method in ['.append', '.pop', '.get', '[']) and any(
                    var in line for var in ['None', 'null']):
                defects.append(Defect(
                    type="logic", message="可能的空值引用错误", line_number=i,
                    severity="MEDIUM", tool="rule", confidence=0.5
                ))

        return defects

    def _defect_to_dict(self, defect: Defect) -> Dict[str, Any]:
        """将Defect对象转换为字典"""
        return {
            "type": defect.type,
            "message": defect.message,
            "line_number": defect.line_number,
            "severity": defect.severity,
            "confidence": defect.confidence
        }

    def analyze_multiple_files(self, files: Dict[str, str]) -> Dict[str, Any]:
        """
        分析多个文件 - AI优先，失败回退规则
        """
        all_defects: List[Defect] = []
        file_defects_list: List[FileDefects] = []

        for file_path, code in files.items():
            defects = self._detect_defects_ai_first(code)
            file_defects = FileDefects(file_path=file_path, defects=defects)
            file_defects_list.append(file_defects)
            all_defects.extend(defects)

        defect_report = DefectReport(
            files=file_defects_list,
            summary={"total_defects": len(all_defects)}
        )

        defect_report_json = defect_report.to_json()
        repair_plan_json = self.decision_manager.analyze(defect_report_json)

        return {
            "defects": [self._defect_to_dict(defect) for defect in all_defects],
            "defect_count": len(all_defects),
            "file_count": len(files),
            "summary": {
                "security": len([d for d in all_defects if d.type == "security"]),
                "syntax": len([d for d in all_defects if d.type == "syntax"]),
                "logic": len([d for d in all_defects if d.type == "logic"])
            },
            "repair_plan": repair_plan_json
        }