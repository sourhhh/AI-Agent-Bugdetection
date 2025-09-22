import os
import re
import json
import tempfile
from typing import List, Dict
from dataclasses import asdict

# 保留您项目原有的模块导入路径（无需修改）
from schemas.project_context import ProjectContext
from schemas.defect_report import Defect, FileDefects, DefectReport
from utils.subprocess_utils import run_command
from core.deepseek_interface import deepseek_client


class DefectDetector:
    """三工具协同缺陷检测器（含精准语法错误临时修复，适配旧版bandit）"""

    def __init__(self):
        # 工具命令配置（bandit无-r参数，适配单个文件检测）
        self.pylint_cmd = ["pylint", "--output-format=json", "{file_path}"]
        self.bandit_cmd = ["bandit", "-f", "json", "{file_path}"]
        self.llm_model = "deepseek-coder"

    def detect(self, project_context_json: str) -> str:
        """主检测入口：串联pylint→临时修复→bandit→LLM→结果合并"""
        try:
            # 解析项目上下文（原始逻辑不变）
            project_context = ProjectContext.from_json(project_context_json)
        except Exception as e:
            print(f"❌ 解析ProjectContext失败：{str(e)}")
            empty_report = DefectReport(
                files=[],
                summary={"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
            )
            return empty_report.to_json()

        # 初始化缺陷报告
        defect_report = DefectReport(files=[], summary={})

        # 遍历所有待检测文件
        for file_path in project_context.python_files:
            if not os.path.exists(file_path):
                print(f"⚠️  跳过不存在的文件：{file_path}")
                continue

            print(f"\n=====================================")
            print(f"🔍 开始检测文件：{os.path.basename(file_path)}")
            print(f"=====================================")

            # 1. 第一步：pylint检测原始文件（捕获真实语法错误）
            pylint_defects = self._detect_with_pylint(file_path)
            print(f"📌 【pylint结果】检测到{len(pylint_defects)}个缺陷")

            # 2. 第二步：判断是否需要生成临时修复文件
            has_syntax_error = any(d.type == "syntax" for d in pylint_defects)
            bandit_file_path = file_path  # 默认用原始文件
            if has_syntax_error:
                # 生成仅含参数修复的临时文件（不破坏其他代码）
                bandit_file_path = self._create_temp_fixed_file(file_path)
                print(f"⚠️  原始文件含语法错误，为bandit生成临时文件：{os.path.basename(bandit_file_path)}")

            # 3. 第三步：bandit检测（临时文件或原始文件）
            bandit_defects = self._detect_with_bandit(bandit_file_path)
            print(f"📌 【bandit结果】检测到{len(bandit_defects)}个缺陷")

            # 4. 第四步：清理临时文件（避免残留）
            if has_syntax_error and os.path.exists(bandit_file_path) and bandit_file_path != file_path:
                os.remove(bandit_file_path)
                print(f"📌 已清理临时文件：{os.path.basename(bandit_file_path)}")

            # 5. 第五步：LLM检测原始文件（保证逻辑错误检测准确）
            llm_defects = self._detect_with_llm(file_path)
            print(f"📌 【LLM结果】检测到{len(llm_defects)}个缺陷")

            # 6. 第六步：合并缺陷（按工具优先级去重）
            merged_defects = self._merge_defects([
                pylint_defects,
                bandit_defects,
                llm_defects
            ])

            # 7. 第七步：添加到最终报告
            if merged_defects:
                defect_report.files.append(
                    FileDefects(file_path=file_path, defects=merged_defects)
                )

        # 生成严重程度汇总
        defect_report.summary = self._generate_severity_summary(defect_report.files)
        print(f"\n📊 【最终汇总】{defect_report.summary}")
        return defect_report.to_json()

    def _create_temp_fixed_file(self, original_path: str) -> str:
        """精准修复：仅修复函数参数内的缺少逗号问题，不破坏其他代码"""
        try:
            # 读取原始代码行
            with open(original_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            fixed_lines = []
            for line_num, line in enumerate(lines, 1):
                # 仅处理函数定义行（def func(...): 格式）
                line_stripped = line.strip()
                if line_stripped.startswith("def ") and "(" in line_stripped and ")" in line_stripped:
                    # 精准提取括号内的参数部分（避免影响def关键字）
                    param_match = re.search(r'\((.*?)\)', line)
                    if param_match:
                        original_params = param_match.group(1)
                        # 仅在参数内替换：字母+空格+字母 → 字母, 空格+字母
                        fixed_params = re.sub(r'(\w+)\s+(\w+)', r'\1, \2', original_params)
                        # 回填修复后的参数到原行（保持其他内容不变）
                        fixed_line = line.replace(original_params, fixed_params)
                        fixed_lines.append(fixed_line)
                        # 打印修复细节（便于调试）
                        print(f"🔧 临时修复第{line_num}行参数：{original_params} → {fixed_params}")
                    else:
                        # 无参数的函数定义，直接保留
                        fixed_lines.append(line)
                else:
                    # 非函数定义行，完全保留原始内容
                    fixed_lines.append(line)

            # 创建系统临时文件（自动分配唯一名称）
            temp_fd, temp_path = tempfile.mkstemp(
                suffix=".py",
                prefix="bandit_fixed_",
                dir=os.path.dirname(original_path)  # 临时文件放在同目录，避免路径问题
            )
            # 写入修复后的内容
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                f.writelines(fixed_lines)

            return temp_path
        except Exception as e:
            print(f"❌ 生成临时文件失败：{str(e)}")
            return original_path  # 失败时回退到原始文件

    def _detect_with_pylint(self, file_path: str) -> List[Defect]:
        """pylint检测：仅捕获语法错误（type=error）"""
        defects = []
        try:
            # 格式化命令
            cmd = [arg.format(file_path=file_path) for arg in self.pylint_cmd]
            # 执行命令并获取结果
            pylint_result = run_command(cmd)

            # 处理pylint的列表格式结果
            if isinstance(pylint_result, list):
                for item in pylint_result:
                    # 仅保留语法错误（type=error，含syntax关键词）
                    if (item.get("type") == "error") and ("syntax" in item.get("message", "").lower()):
                        defect = Defect(
                            type="syntax",
                            message=f"[pylint] {item['message'].strip()}",
                            line_number=item.get("line", -1),
                            severity="HIGH",  # 语法错误均为高优先级
                            tool="pylint",
                            confidence=0.9  # pylint语法检测可信度高
                        )
                        defects.append(defect)
        except Exception as e:
            print(f"❌ pylint执行异常：{str(e)}")
        return defects

    def _detect_with_bandit(self, file_path: str) -> List[Defect]:
        """bandit检测：仅捕获安全漏洞（临时文件无语法错误）"""
        defects = []
        try:
            # 格式化命令
            cmd = [arg.format(file_path=file_path) for arg in self.bandit_cmd]
            # 执行命令并获取结果
            bandit_result = run_command(cmd)

            # 处理bandit的字典格式结果
            if isinstance(bandit_result, dict):
                # 即使有非致命错误，只要results非空就解析
                if "results" in bandit_result and bandit_result["results"]:
                    for issue in bandit_result["results"]:
                        # 标准化严重程度（bandit返回小写，统一为大写）
                        severity = issue["issue_severity"].upper()
                        if severity not in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
                            severity = "MEDIUM"

                        defect = Defect(
                            type="security",
                            message=f"[bandit] {issue['issue_text'].strip()}",
                            line_number=issue.get("line_number", -1),
                            severity=severity,
                            tool="bandit",
                            confidence=0.95  # bandit安全检测可信度最高
                        )
                        defects.append(defect)
                else:
                    # 无结果时打印提示（非错误）
                    print(f"⚠️ bandit未检测到安全漏洞（文件：{os.path.basename(file_path)}）")
        except Exception as e:
            print(f"❌ bandit执行异常：{str(e)}")
        return defects

    def _detect_with_llm(self, file_path: str) -> List[Defect]:
        """LLM检测：捕获语法+安全+逻辑三类缺陷（基于原始文件）"""
        defects = []
        try:
            # 读取原始代码内容
            with open(file_path, "r", encoding="utf-8") as f:
                code = f.read()
            if not code:
                print(f"⚠️ LLM检测失败：文件为空（{os.path.basename(file_path)}）")
                return defects

            # 精准提示词（明确要求三类缺陷+标准化输出）
            prompt = f"""
你是严格的Python代码缺陷检测专家，必须基于以下代码检测3类缺陷：
1. 语法错误：如函数参数缺少逗号、缩进错误等
2. 安全漏洞：如使用eval处理用户输入、硬编码敏感信息等
3. 逻辑错误：如空列表除零、索引越界、条件判断错误等

【输出强制要求】：
1. 仅返回JSON数组，无任何多余文本（如解释、换行）
2. 每个数组元素必须包含以下6个字段（字段值严格匹配要求）：
   - "type": 缺陷类型（仅允许：syntax/security/logic/code_smell）
   - "message": 缺陷描述（含位置+原因+影响，中文）
   - "line_number": 缺陷行号（整数，无法确定则填-1）
   - "severity": 严重程度（仅允许：CRITICAL/HIGH/MEDIUM/LOW）
   - "tool": 固定值"llm"
   - "confidence": 固定值0.8

【待检测代码】：
{code}
            """

            # 调用LLM接口
            llm_response = deepseek_client.query(prompt, model=self.llm_model)
            if not llm_response:
                print(f"⚠️ LLM无响应（{os.path.basename(file_path)}）")
                return defects

            # 提取JSON内容（处理LLM可能的多余文本）
            json_match = re.search(r'\[.*\]', llm_response, re.DOTALL)
            if not json_match:
                print(f"⚠️ LLM输出无有效JSON（前50字符：{llm_response[:50]}）")
                return defects

            # 解析JSON并标准化字段
            llm_defects_json = json.loads(json_match.group())
            for d in llm_defects_json:
                # 强制标准化type字段
                valid_types = ["syntax", "security", "logic", "code_smell"]
                defect_type = d.get("type", "code_smell")
                defect_type = defect_type if defect_type in valid_types else "code_smell"

                # 强制标准化severity字段
                valid_severities = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
                severity = d.get("severity", "MEDIUM").upper()
                severity = severity if severity in valid_severities else "MEDIUM"

                # 强制标准化line_number字段
                line_number = -1
                if isinstance(d.get("line_number"), (int, float)):
                    line_number = int(d["line_number"])

                # 创建Defect对象
                defect = Defect(
                    type=defect_type,
                    message=f"[llm] {d.get('message', '未描述的缺陷').strip()}",
                    line_number=line_number,
                    severity=severity,
                    tool="llm",
                    confidence=0.8
                )
                defects.append(defect)

        except json.JSONDecodeError:
            print(f"❌ LLM输出JSON格式错误（内容：{json_match.group()[:100]}）")
        except Exception as e:
            print(f"❌ LLM执行异常：{str(e)}")
        return defects

    def _merge_defects(self, defects_list: List[List[Defect]]) -> List[Defect]:
        """合并缺陷：按工具优先级去重，按行号排序"""
        merged_defects = {}
        # 工具优先级：bandit（安全）> pylint（语法）> llm（逻辑）
        tool_priority = {"bandit": 3, "pylint": 2, "llm": 1}

        # 扁平化所有缺陷
        all_defects = [defect for sublist in defects_list for defect in sublist]

        for defect in all_defects:
            # 去重键：行号+类型+消息前缀（避免同一缺陷重复报告）
            deduplicate_key = f"{defect.line_number}_{defect.type}_{defect.message[:30]}"

            # 仅保留优先级最高的工具报告的缺陷
            if deduplicate_key not in merged_defects:
                merged_defects[deduplicate_key] = defect
            else:
                existing_priority = tool_priority[merged_defects[deduplicate_key].tool]
                current_priority = tool_priority[defect.tool]
                if current_priority > existing_priority:
                    merged_defects[deduplicate_key] = defect

        # 按行号升序排序，便于阅读
        return sorted(merged_defects.values(), key=lambda x: x.line_number)

    def _generate_severity_summary(self, file_defects_list: List[FileDefects]) -> Dict[str, int]:
        """生成缺陷严重程度汇总（按CRITICAL→HIGH→MEDIUM→LOW排序）"""
        summary = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for file_defects in file_defects_list:
            for defect in file_defects.defects:
                if defect.severity in summary:
                    summary[defect.severity] += 1
        return summary