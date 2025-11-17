import os
import re
import json
import tempfile
import time
import sys
import logging
import threading
from typing import List, Dict, Set, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from schemas.project_context import ProjectContext
from schemas.defect_report import Defect, FileDefects, DefectReport
from utils.subprocess_runner import run_command
from core.deepseek_interface import deepseek_client

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("defect_detection.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class DefectDetector:
    def __init__(self):
        self.pylint_cmd = [
            "pylint",
            "--output-format=json",
            "--enable=unused-import",
            "--enable=bad-indentation",
            "--enable=unreachable",
            "--enable=duplicate-code",
            "--enable=missing-docstring",
            "--enable=unused-variable",
            "{file_path}"
        ]
        self.bandit_cmd = ["bandit", "-f", "json", "{file_path}"]
        self.llm_model = "deepseek-coder"
        self.llm_max_retries = 1  # 减少到1次重试避免长时间等待
        self.llm_retry_delay = 2  # 减少重试延迟
        self.llm_request_timeout = 30  # 进一步减少超时时间到30秒
        self.performance_thresholds = {
            "long_function": 50,
            "high_complexity": 10,
        }
        self.max_workers = 2  # 保持较低并发避免API压力
        self.llm_concurrent_semaphore = threading.Semaphore(1)  # 减少LLM并发调用为1，避免API限制

    def detect(self, project_context_json: str) -> str:
        """主检测函数，接收项目上下文并返回缺陷报告"""
        try:
            logger.info("开始解析项目上下文")
            project_context = ProjectContext.from_json(project_context_json)
        except Exception as e:
            logger.error(f"解析ProjectContext失败：{str(e)}")
            empty_report = DefectReport(files=[], summary={})
            return empty_report.to_json()

        defect_report = DefectReport(files=[], summary={})

        # 只处理Python文件
        python_files = project_context.pure_python_files

        total_files = len(python_files)
        logger.info(f"开始检测项目，共{total_files}个Python文件")

        # 使用线程池并行处理所有文件检测
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._process_single_file, file_path): file_path
                for file_path in python_files
            }

            completed = 0
            for future in as_completed(futures):
                file_path = futures[future]
                completed += 1
                try:
                    file_defects = future.result()
                    if file_defects:
                        defect_report.files.append(file_defects)
                    progress = (completed / total_files) * 100
                    logger.info(f"检测进度：{completed}/{total_files} ({progress:.1f}%) - {os.path.basename(file_path)}")
                except Exception as e:
                    logger.error(f"处理文件{file_path}时出错：{str(e)}")

        # 生成统计信息
        defect_report.summary = self._generate_severity_summary(defect_report.files)
        type_summary = self._generate_type_summary(defect_report.files)

        logger.info(f"【类型统计】{type_summary}")
        logger.info(f"【严重程度汇总】{defect_report.summary}")

        return defect_report.to_json()

    def _process_single_file(self, file_path: str) -> FileDefects:
        """处理单个文件的检测，供并行执行"""
        if not os.path.exists(file_path):
            logger.warning(f"跳过不存在的文件：{file_path}")
            return None

        file_name = os.path.basename(file_path)
        logger.info(f"开始检测文件：{file_name}")

        # 只处理Python文件
        if file_path.endswith('.py'):
            return self._process_python_file(file_path)
        else:
            logger.warning(f"不支持的文件类型：{file_name}")
            return None

    def _process_python_file(self, file_path: str) -> FileDefects:
        """处理Python文件的检测"""
        file_name = os.path.basename(file_path)
        logger.info(f"开始Python文件检测：{file_name}")

        # pylint检测
        pylint_defects = self._detect_with_pylint(file_path)
        logger.info(f"[pylint结果] {file_name}检测到{len(pylint_defects)}个缺陷")

        # 临时修复处理
        has_syntax_error = any(d.type == "syntax" for d in pylint_defects)
        bandit_file_path = file_path
        if has_syntax_error:
            bandit_file_path = self._create_temp_fixed_file(file_path)
            logger.warning(f"原始文件含语法错误，为bandit生成临时文件：{os.path.basename(bandit_file_path)}")

        # bandit检测
        bandit_defects = self._detect_with_bandit(bandit_file_path)
        logger.info(f"[bandit结果] {file_name}检测到{len(bandit_defects)}个缺陷")

        # 清理临时文件
        if has_syntax_error and os.path.exists(bandit_file_path) and bandit_file_path != file_path:
            os.remove(bandit_file_path)
            logger.info(f"已清理临时文件：{os.path.basename(bandit_file_path)}")

        # LLM检测 - 增加更多调试信息
        logger.info(f"[LLM开始] 准备检测文件：{file_name}")
        llm_defects = self._detect_with_llm(file_path)
        logger.info(f"[LLM结果] {file_name}检测到{len(llm_defects)}个缺陷")

        # 性能问题检测
        performance_defects = self._detect_performance_issues(file_path)
        logger.info(f"[性能检测结果] {file_name}检测到{len(performance_defects)}个潜在问题")

        # 合并缺陷
        merged_defects = self._merge_defects([
            pylint_defects,
            bandit_defects,
            llm_defects,
            performance_defects
        ])

        if merged_defects:
            for defect in merged_defects:
                defect.file_name = file_name  # 添加文件名属性
            return FileDefects(file_path=file_path, defects=merged_defects)

        return None

    def _create_temp_fixed_file(self, original_path: str) -> str:
        """创建修复了基本语法错误的临时文件，用于bandit检测"""
        try:
            with open(original_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            fixed_lines = []
            for line_num, line in enumerate(lines, 1):
                line_stripped = line.strip()
                # 修复参数缺少逗号问题
                if line_stripped.startswith("def ") and "(" in line_stripped and ")" in line_stripped:
                    param_match = re.search(r'\((.*?)\)', line)
                    if param_match:
                        original_params = param_match.group(1)
                        fixed_params = re.sub(r'(\w+)\s+(\w+)', r'\1, \2', original_params)
                        if original_params != fixed_params:
                            fixed_line = line.replace(original_params, fixed_params)
                            fixed_lines.append(fixed_line)
                            logger.debug(f"临时修复第{line_num}行参数：{original_params} → {fixed_params}")
                        else:
                            fixed_lines.append(line)
                    else:
                        fixed_lines.append(line)
                # 修复未闭合括号问题
                elif '{' in line_stripped and '}' not in line_stripped:
                    fixed_line = line.rstrip() + '}\n'
                    fixed_lines.append(fixed_line)
                    logger.debug(f"临时修复第{line_num}行：补充闭合花括号")
                elif '(' in line_stripped and ')' not in line_stripped:
                    fixed_line = line.rstrip() + ')\n'
                    fixed_lines.append(fixed_line)
                    logger.debug(f"临时修复第{line_num}行：补充闭合圆括号")
                else:
                    fixed_lines.append(line)

            temp_fd, temp_path = tempfile.mkstemp(
                suffix=".py",
                prefix="bandit_fixed_",
                dir=os.path.dirname(original_path)
            )
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                f.writelines(fixed_lines)
            return temp_path
        except Exception as e:
            logger.error(f"生成临时文件失败：{str(e)}")
            return original_path

    def _detect_with_pylint(self, file_path: str) -> List[Defect]:
        """使用pylint检测代码缺陷"""
        defects = []
        try:
            cmd = [arg.format(file_path=file_path) for arg in self.pylint_cmd]
            logger.debug(f"执行pylint命令：{' '.join(cmd)}")
            pylint_result = run_command(cmd)

            if isinstance(pylint_result, list):
                for item in pylint_result:
                    if item.get("type") in ["error", "warning"]:
                        # 细化缺陷类型判断
                        defect_type = "syntax" if item.get("type") == "error" else "code_smell"

                        if "Unused import" in item.get("message", ""):
                            defect_type = "code_smell"
                        if "bad indentation" in item.get("message", "").lower():
                            defect_type = "syntax"
                        if "duplicate code" in item.get("message", "").lower():
                            defect_type = "code_smell"
                        if "missing docstring" in item.get("message", "").lower():
                            defect_type = "code_smell"
                        if "unused variable" in item.get("message", "").lower():
                            defect_type = "code_smell"

                        # 细化严重程度
                        severity = "HIGH" if item.get("type") == "error" else "LOW"
                        if "Unable to import" in item.get("message", ""):
                            severity = "HIGH"
                        if "duplicate code" in item.get("message", "").lower():
                            severity = "MEDIUM"

                        defect = Defect(
                            type=defect_type,
                            message=f"[pylint] {item['message'].strip()}",
                            line_number=item.get("line", -1),
                            severity=severity,
                            tool="pylint",
                            confidence=0.9
                        )
                        defects.append(defect)
        except Exception as e:
            logger.error(f"pylint执行异常：{str(e)}")
        return defects

    def _detect_with_bandit(self, file_path: str) -> List[Defect]:
        """使用bandit检测安全缺陷"""
        defects = []
        try:
            cmd = [arg.format(file_path=file_path) for arg in self.bandit_cmd]
            logger.debug(f"执行bandit命令：{' '.join(cmd)}")
            bandit_result = run_command(cmd)

            if isinstance(bandit_result, dict) and "results" in bandit_result:
                for issue in bandit_result["results"]:
                    severity = issue["issue_severity"].upper()
                    if severity not in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
                        severity = "MEDIUM"

                    # 细化缺陷类型
                    defect_type = "security"
                    if "assert" in issue["issue_text"].lower():
                        defect_type = "code_smell"
                    if "SQL injection" in issue["issue_text"]:
                        severity = "CRITICAL"
                    if "pseudo-random generators" in issue["issue_text"]:
                        severity = "HIGH"

                    defect = Defect(
                        type=defect_type,
                        message=f"[bandit] {issue['issue_text'].strip()}",
                        line_number=issue.get("line_number", -1),
                        severity=severity,
                        tool="bandit",
                        confidence=0.95
                    )
                    defects.append(defect)
            else:
                logger.info(f"bandit未检测到安全漏洞（文件：{os.path.basename(file_path)}）")
        except Exception as e:
            logger.error(f"bandit执行异常：{str(e)}")
        return defects

    def _detect_with_llm(self, file_path: str) -> List[Defect]:
        """使用LLM模型检测代码缺陷，增强稳定性处理"""
        defects = []
        retry_count = 0
        file_name = os.path.basename(file_path)
        logger.debug(f"开始LLM检测文件: {file_name}")

        # 特殊处理测试文件
        is_test_file = file_name.startswith("test_")

        # 读取文件内容（提前读取，避免重试时重复读取）
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code = f.read()
        except UnicodeDecodeError:
            with open(file_path, "r", encoding="latin-1") as f:
                code = f.read()
        except Exception as e:
            logger.error(f"读取文件{file_name}失败: {str(e)}")
            return self._get_fallback_defects(is_test_file, file_name, "文件读取失败")

        if not code:
            logger.warning(f"LLM检测失败：文件为空（{file_name}）")
            return self._get_fallback_defects(is_test_file, file_name, "文件内容为空")

        # 限制代码长度以提高处理速度和成功率
        max_code_length = 4000  # 进一步减少代码长度
        if len(code) > max_code_length:
            logger.info(f"文件{file_name}过长，截断至{max_code_length}字符进行LLM检测")
            code = code[:max_code_length] + "\n...[文件内容已截断]..."

        # 构建提示词
        prompt = self._build_llm_prompt(file_name, is_test_file, code)

        while retry_count < self.llm_max_retries:
            # 控制并发请求数
            with self.llm_concurrent_semaphore:
                try:
                    logger.debug(f"向LLM发送请求检测文件：{file_name}（重试次数：{retry_count}）")

                    # 使用线程超时控制避免无限等待
                    result = self._call_llm_with_timeout(prompt)

                    if result is None:
                        raise TimeoutError(f"LLM调用超时（{self.llm_request_timeout}秒）")

                    llm_response = result

                    # 检查响应是否有效
                    if not llm_response or not isinstance(llm_response, str):
                        raise ValueError(f"LLM返回无效响应: {str(llm_response)[:100]}")

                    # 记录响应预览
                    response_preview = llm_response[:500] + "..." if len(llm_response) > 500 else llm_response
                    logger.debug(f"LLM原始响应: {response_preview}")

                    # 解析JSON响应
                    llm_defects_json = self._parse_llm_response(llm_response)
                    if not isinstance(llm_defects_json, list):
                        raise ValueError(f"LLM返回的不是数组: {type(llm_defects_json)}")

                    # 处理解析结果
                    for d in llm_defects_json:
                        # 验证类型
                        valid_types = ["syntax", "security", "logic", "code_smell", "performance"]
                        defect_type = d.get("type", "code_smell")
                        defect_type = defect_type if defect_type in valid_types else "code_smell"

                        # 验证严重程度
                        valid_severities = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
                        severity = d.get("severity", "MEDIUM").upper()
                        severity = severity if severity in valid_severities else "MEDIUM"

                        # 处理行号
                        try:
                            line_number = int(d.get("line_number", -1))
                        except (ValueError, TypeError):
                            line_number = -1

                        defect = Defect(
                            type=defect_type,
                            message=f"[llm] {d.get('message', '未描述的缺陷').strip()}",
                            line_number=line_number,
                            severity=severity,
                            tool="llm",
                            confidence=0.8
                        )
                        defects.append(defect)

                    logger.debug(f"LLM成功检测到{len(defects)}个缺陷 in {file_name}")
                    return defects

                except (TimeoutError, ConnectionError) as e:
                    # 网络或超时错误，适合重试
                    retry_count += 1
                    logger.warning(f"LLM调用超时/连接错误 (重试 {retry_count}/{self.llm_max_retries}): {str(e)}")
                    if retry_count < self.llm_max_retries:
                        sleep_time = self.llm_retry_delay * retry_count  # 线性退避
                        logger.info(f"等待{sleep_time}秒后重试...")
                        time.sleep(sleep_time)
                    else:
                        logger.error(f"LLM调用达到最大重试次数，失败原因: {str(e)}")
                        break

                except (json.JSONDecodeError, ValueError) as e:
                    # JSON解析错误或响应内容无效
                    retry_count += 1
                    logger.warning(f"LLM响应解析错误 (重试 {retry_count}/{self.llm_max_retries}): {str(e)}")
                    if retry_count < self.llm_max_retries:
                        sleep_time = self.llm_retry_delay * retry_count
                        logger.info(f"等待{sleep_time}秒后重试...")
                        time.sleep(sleep_time)
                    else:
                        logger.error(f"LLM响应解析失败，达到最大重试次数")
                        break

                except Exception as e:
                    # 其他未知错误，记录并退出重试
                    logger.error(f"LLM执行异常: {str(e)}", exc_info=True)
                    break

        # 所有重试都失败，返回 fallback 缺陷
        return self._get_fallback_defects(is_test_file, file_name, "LLM服务调用失败")

    def _call_llm_with_timeout(self, prompt):
        """带超时控制的LLM调用"""
        result = [None]  # 用列表存储结果，以便在嵌套函数中修改

        def _target():
            try:
                result[0] = deepseek_client.query(prompt, model=self.llm_model)
            except Exception as e:
                result[0] = e  # 存储异常

        thread = threading.Thread(target=_target)
        thread.start()
        thread.join(self.llm_request_timeout)

        if thread.is_alive():
            logger.warning(f"LLM调用超时（{self.llm_request_timeout}秒）")
            return None

        if isinstance(result[0], Exception):
            raise result[0]  # 抛出调用过程中发生的异常

        return result[0]

    def _parse_llm_response(self, response):
        """解析LLM响应，增强容错性"""
        try:
            # 尝试直接解析整个响应
            return json.loads(response)
        except json.JSONDecodeError:
            # 尝试提取JSON数组（处理可能的多余文本）
            json_match = re.search(r'\[\s*\{.*\}\s*\]', response, re.DOTALL)
            if not json_match:
                raise json.JSONDecodeError("无法找到有效的JSON数组", response, 0)

            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError as e:
                raise e

    def _build_llm_prompt(self, file_name, is_test_file, code):
        """构建更清晰的LLM提示词"""
        return f"""
你是严格的Python代码缺陷检测专家，正在检测文件：{file_name}
{"这是一个测试文件，需要重点检查测试质量和完整性问题。" if is_test_file else ""}

请检测以下类型的缺陷：
- syntax: 语法错误（参数缺少逗号、缩进错误、未闭合括号等）
- security: 安全漏洞（硬编码敏感信息、SQL注入风险、不安全随机数等）
- logic: 逻辑错误（资源未释放、条件判断错误、除零风险等）
- code_smell: 代码异味（未使用导入、重复代码、测试不完整、函数过长等）
- performance: 性能问题（循环效率低、冗余计算、大文件一次性加载等）

【输出强制要求】：
1. 仅返回JSON数组，无任何多余文本、解释或说明
2. JSON数组中的每个元素必须包含以下字段：
   - "type"：必须是上述五种类型之一
   - "message"：详细的缺陷描述
   - "line_number"：问题所在的行号（整数）
   - "severity"：必须是CRITICAL/HIGH/MEDIUM/LOW之一
   - "tool"：固定为"llm"
   - "confidence"：固定为0.8

如果没有检测到任何缺陷，请返回空数组[]

【待检测代码】：
{code}
        """

    def _get_fallback_defects(self, is_test_file, file_name, reason):
        """当LLM调用失败时返回的备用缺陷信息"""
        fallback = []
        if is_test_file:
            fallback.append(Defect(
                type="code_smell",
                message=f"[llm] 检测服务暂时不可用：{reason}，建议检查测试覆盖率",
                line_number=1,
                severity="LOW",
                tool="llm",
                confidence=0.3
            ))
        else:
            fallback.append(Defect(
                type="code_smell",
                message=f"[llm] 检测服务暂时不可用：{reason}，建议手动检查代码",
                line_number=1,
                severity="LOW",
                tool="llm",
                confidence=0.3
            ))
        return fallback

    def _detect_performance_issues(self, file_path: str) -> List[Defect]:
        """检测潜在的性能问题"""
        defects = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code = f.read()

            lines = code.split('\n')
            file_name = os.path.basename(file_path)

            # 检测过长函数
            function_pattern = re.compile(r'def\s+\w+\s*\(.*?\)\s*:')
            function_starts = []

            for i, line in enumerate(lines):
                if function_pattern.search(line):
                    function_starts.append(i + 1)  # 行号从1开始

            # 分析每个函数的长度
            for start_line in function_starts:
                # 查找下一个函数开始或文件结束作为当前函数的结束
                end_line = len(lines) + 1  # 默认到文件末尾
                for next_start in function_starts:
                    if next_start > start_line:
                        end_line = next_start - 1
                        break

                function_length = end_line - start_line
                if function_length > self.performance_thresholds["long_function"]:
                    defects.append(Defect(
                        type="performance",
                        message=f"[performance] 函数过长（{function_length}行），可能影响性能和可维护性",
                        line_number=start_line,
                        severity="MEDIUM",
                        tool="detector",
                        confidence=0.7
                    ))

            # 检测大文件读取模式
            for i, line in enumerate(lines):
                line_num = i + 1
                if re.search(r'open\(.*?\)\.read\(\)', line) and \
                        (re.search(r'\.txt|\.csv|\.log', line) or
                         not re.search(r'small|tiny|sample', line, re.IGNORECASE)):
                    defects.append(Defect(
                        type="performance",
                        message="[performance] 可能一次性读取大文件，建议使用迭代方式处理",
                        line_number=line_num,
                        severity="MEDIUM",
                        tool="detector",
                        confidence=0.75
                    ))

            logger.debug(f"性能检测完成，{file_name}发现{len(defects)}个潜在问题")

        except Exception as e:
            logger.error(f"性能问题检测异常：{str(e)}")

        return defects

    def _merge_defects(self, defects_list: List[List[Defect]]) -> List[Defect]:
        """合并多个工具检测到的缺陷"""
        merged_defects_map = {}
        tool_priority = {"bandit": 4, "pylint": 3, "llm": 2, "detector": 1}
        all_defects = [defect for sublist in defects_list for defect in sublist]

        for defect in all_defects:
            key = f"{defect.type}_{defect.line_number}_{defect.message[:50]}"

            if key not in merged_defects_map or tool_priority.get(defect.tool, 0) > tool_priority.get(
                    merged_defects_map[key].tool, 0):
                merged_defects_map[key] = defect

        return sorted(merged_defects_map.values(), key=lambda x: x.line_number)

    def _get_unique_defects(self, file_defects_list: List[FileDefects]) -> List[Defect]:
        """获取去重后的缺陷列表"""
        unique_defects = []
        seen: Set[Tuple[str, int, str, str]] = set()

        for file_defects in file_defects_list:
            file_name = os.path.basename(file_defects.file_path)
            for defect in file_defects.defects:
                key = (file_name, defect.line_number, defect.type, defect.message[:50])
                if key not in seen:
                    seen.add(key)
                    unique_defects.append(defect)

        return unique_defects

    def _count_matched_defects(self, detected_defects: List[Defect], known_defects: List[Tuple[str, str, int]]) -> int:
        """匹配已知缺陷"""
        matched_count = 0
        detected_matched = set()
        return matched_count

    def _generate_severity_summary(self, file_defects_list: List[FileDefects]) -> Dict[str, int]:
        """生成按严重程度统计的摘要"""
        summary = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for file_defects in file_defects_list:
            for defect in file_defects.defects:
                if defect.severity in summary:
                    summary[defect.severity] += 1
        return summary

    def _generate_type_summary(self, file_defects_list: List[FileDefects]) -> Dict[str, int]:
        """生成按类型统计的摘要"""
        type_summary = {
            "syntax": 0,
            "security": 0,
            "logic": 0,
            "code_smell": 0,
            "performance": 0,
        }
        for file_defects in file_defects_list:
            for defect in file_defects.defects:
                if defect.type in type_summary:
                    type_summary[defect.type] += 1
        return type_summary

    def _get_known_defects(self):
        """已知缺陷库"""
        return []