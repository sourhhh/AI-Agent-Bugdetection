import os
import re
import json
import time
import logging
import threading
import subprocess
from typing import List, Dict, Optional
from xml.etree import ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

from schemas.project_context import ProjectContext
from schemas.defect_report import Defect, FileDefects, DefectReport
from core.deepseek_interface import deepseek_client

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("defect_detection_java.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class DefectDetectorJava:
    def __init__(self):
        self.checkstyle_config = os.getenv("CHECKSTYLE_CONFIG", "/google_checks.xml")
        self.checkstyle_version_cmd = ["checkstyle", "-version"]
        self.checkstyle_cmd = [
            "checkstyle",
            "-f", "xml",
            "-c", self.checkstyle_config,
            "{file_path}"
        ]
        # local jar fallback (downloaded into ./tools)
        self.checkstyle_jar_path = os.path.join(os.path.dirname(__file__), "..", "tools", "checkstyle-all.jar")
        self.pmd_ruleset = os.getenv("PMD_RULESET", "category/java/bestpractices.xml")
        self.pmd_version_cmd = ["pmd", "-version"]
        self.pmd_cmd = [
            "pmd",
            "-d", "{file_path}",
            "-R", self.pmd_ruleset,
            "-f", "xml"
        ]
        self.llm_model = "deepseek-coder"
        self.llm_max_retries = 1
        self.llm_retry_delay = 2
        self.llm_request_timeout = 30
        self.max_workers = 2
        self.llm_concurrent_semaphore = threading.Semaphore(1)
        self.style_thresholds = {
            "max_line_length": 140,
            "long_method": 80,
        }
        self.performance_thresholds = {
            "long_method": 120,
            "nested_loop_depth": 3,
            "string_concat_threshold": 3,
        }

    def detect(self, project_context_json: str) -> str:
        try:
            logger.info("开始解析Java项目上下文")
            project_context = ProjectContext.from_json(project_context_json)
        except Exception as e:
            logger.error(f"解析ProjectContext失败：{str(e)}")
            empty_report = DefectReport(files=[], summary={})
            return empty_report.to_json()

        defect_report = DefectReport(files=[], summary={})
        java_files = project_context.java_files
        total_files = len(java_files)
        logger.info(f"开始检测Java项目，共{total_files}个Java文件")

        if total_files == 0:
            logger.warning("项目中未找到Java文件，返回空报告")
            defect_report.summary = self._generate_severity_summary([])
            return defect_report.to_json()

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._process_single_file, file_path): file_path
                for file_path in java_files
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

        defect_report.summary = self._generate_severity_summary(defect_report.files)
        type_summary = self._generate_type_summary(defect_report.files)
        logger.info(f"【类型统计】{type_summary}")
        logger.info(f"【严重程度汇总】{defect_report.summary}")

        return defect_report.to_json()

    def _process_single_file(self, file_path: str) -> FileDefects:
        if not os.path.exists(file_path):
            logger.warning(f"跳过不存在的文件：{file_path}")
            return None

        file_name = os.path.basename(file_path)
        logger.info(f"开始检测Java文件：{file_name}")
        return self._process_java_file(file_path)

    def _process_java_file(self, file_path: str) -> FileDefects:
        file_name = os.path.basename(file_path)

        checkstyle_defects = self._detect_with_checkstyle(file_path)
        logger.info(f"[checkstyle结果] {file_name}检测到{len(checkstyle_defects)}个缺陷")

        pmd_defects = self._detect_with_pmd(file_path)
        logger.info(f"[pmd结果] {file_name}检测到{len(pmd_defects)}个缺陷")

        llm_defects = self._detect_with_llm(file_path)
        logger.info(f"[LLM结果] {file_name}检测到{len(llm_defects)}个缺陷")

        performance_defects = self._detect_performance_issues(file_path)
        logger.info(f"[性能检测结果] {file_name}检测到{len(performance_defects)}个潜在问题")

        merged_defects = self._merge_defects([
            checkstyle_defects,
            pmd_defects,
            llm_defects,
            performance_defects
        ])

        if merged_defects:
            for defect in merged_defects:
                defect.file_name = file_name
            return FileDefects(file_path=file_path, defects=merged_defects)

        return None

    def _detect_with_checkstyle(self, file_path: str) -> List[Defect]:
        # Prefer system checkstyle CLI if available
        if self._is_tool_available(self.checkstyle_version_cmd):
            cmd = [arg.format(file_path=file_path) for arg in self.checkstyle_cmd]
            raw_output = self._run_tool(cmd)
            if raw_output:
                parsed = self._parse_checkstyle_xml(raw_output, file_path)
                if parsed:
                    return parsed

        # Fallback to local jar if present
        jar_path = os.path.normpath(self.checkstyle_jar_path)
        if os.path.exists(jar_path):
            jar_cmd = ["java", "-jar", jar_path, "-f", "xml", "-c", os.path.join(os.path.dirname(jar_path), "google_checks.xml"), file_path]
            raw_output = self._run_tool(jar_cmd)
            if raw_output:
                parsed = self._parse_checkstyle_xml(raw_output, file_path)
                if parsed:
                    return parsed

        logger.warning("Checkstyle 未可用或未返回可解析结果，使用启发式规则代替")
        return self._simulate_checkstyle(file_path)

    def _detect_with_pmd(self, file_path: str) -> List[Defect]:
        # Prefer system pmd if available
        if self._is_tool_available(self.pmd_version_cmd):
            cmd = [arg.format(file_path=file_path) for arg in self.pmd_cmd]
            raw_output = self._run_tool(cmd)
            if raw_output:
                parsed = self._parse_pmd_xml(raw_output, file_path)
                if parsed:
                    return parsed

        # Try local pmd in tools directory (extracted pmd-dist-*/bin/pmd.bat)
        tools_root = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
        local_pmd = None
        try:
            for root, dirs, files in os.walk(os.path.join(tools_root, 'pmd')):
                if 'pmd.bat' in files or 'pmd' in files:
                    candidate = os.path.join(root, 'pmd.bat') if 'pmd.bat' in files else os.path.join(root, 'pmd')
                    local_pmd = candidate
                    break
        except Exception:
            local_pmd = None

        if local_pmd and os.path.exists(local_pmd):
            cmd = [local_pmd, '-d', file_path, '-R', self.pmd_ruleset, '-f', 'xml']
            raw_output = self._run_tool(cmd)
            if raw_output:
                parsed = self._parse_pmd_xml(raw_output, file_path)
                if parsed:
                    return parsed

        logger.warning("PMD 未可用或未返回可解析结果，使用启发式规则代替")
        return self._heuristic_java_issues(file_path)

    def _simulate_checkstyle(self, file_path: str) -> List[Defect]:
        defects: List[Defect] = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            logger.error(f"读取Java文件失败：{str(e)}")
            return defects

        for idx, line in enumerate(lines, start=1):
            stripped = line.rstrip("\n")
            if len(stripped) > self.style_thresholds["max_line_length"]:
                defects.append(Defect(
                    type="code_smell",
                    message="[checkstyle] 行过长，建议拆分或换行",
                    line_number=idx,
                    severity="LOW",
                    tool="checkstyle",
                    confidence=0.7
                ))
            if stripped.endswith(" "):
                defects.append(Defect(
                    type="code_smell",
                    message="[checkstyle] 行尾存在多余空格",
                    line_number=idx,
                    severity="LOW",
                    tool="checkstyle",
                    confidence=0.6
                ))
            if "\t" in line:
                defects.append(Defect(
                    type="code_smell",
                    message="[checkstyle] 使用了制表符，建议替换为空格",
                    line_number=idx,
                    severity="LOW",
                    tool="checkstyle",
                    confidence=0.6
                ))
            stripped_inner = stripped.strip()
            if stripped_inner.startswith("// TODO"):
                defects.append(Defect(
                    type="code_smell",
                    message="[checkstyle] 包含未处理的TODO注释",
                    line_number=idx,
                    severity="LOW",
                    tool="checkstyle",
                    confidence=0.5
                ))
            if stripped_inner.startswith("import") and stripped_inner.endswith(".*;"):
                defects.append(Defect(
                    type="code_smell",
                    message="[checkstyle] 使用通配符导入，建议显式导入所需类",
                    line_number=idx,
                    severity="LOW",
                    tool="checkstyle",
                    confidence=0.7
                ))

        method_ranges = self._find_method_ranges(lines)
        for start, end in method_ranges:
            length = end - start + 1
            if length > self.style_thresholds["long_method"]:
                defects.append(Defect(
                    type="code_smell",
                    message=f"[checkstyle] 方法过长（{length}行），建议拆分",
                    line_number=start,
                    severity="MEDIUM",
                    tool="checkstyle",
                    confidence=0.75
                ))

        return defects

    def _heuristic_java_issues(self, file_path: str) -> List[Defect]:
        defects: List[Defect] = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code = f.read()
        except Exception as e:
            logger.error(f"读取Java文件失败：{str(e)}")
            return defects

        lines = code.split("\n")
        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()

            if "Runtime.getRuntime().exec" in stripped:
                defects.append(Defect(
                    type="security",
                    message="[pmd] 使用Runtime.exec存在命令注入风险",
                    line_number=idx,
                    severity="HIGH",
                    tool="pmd",
                    confidence=0.85
                ))

            if "System.exit(" in stripped:
                defects.append(Defect(
                    type="code_smell",
                    message="[pmd] 在库代码中调用System.exit可能导致进程被意外终止",
                    line_number=idx,
                    severity="MEDIUM",
                    tool="pmd",
                    confidence=0.75
                ))

            if re.search(r"password\s*=\s*\".+\"", stripped, re.IGNORECASE):
                defects.append(Defect(
                    type="security",
                    message="[pmd] 检测到疑似硬编码密码",
                    line_number=idx,
                    severity="CRITICAL",
                    tool="pmd",
                    confidence=0.9
                ))

            if "Thread.sleep(" in stripped and "catch" not in stripped:
                defects.append(Defect(
                    type="concurrency",
                    message="[pmd] Thread.sleep缺少InterruptedException处理",
                    line_number=idx,
                    severity="MEDIUM",
                    tool="pmd",
                    confidence=0.7
                ))

            if stripped.startswith("catch") and "{" in stripped:
                if self._is_empty_catch(lines, idx - 1):
                    defects.append(Defect(
                        type="code_smell",
                        message="[pmd] 捕获异常但未处理，建议添加日志或抛出",
                        line_number=idx,
                        severity="MEDIUM",
                        tool="pmd",
                        confidence=0.8
                    ))

            if "executeQuery" in stripped and "+" in stripped:
                defects.append(Defect(
                    type="security",
                    message="[pmd] SQL拼接可能导致注入风险，建议使用PreparedStatement",
                    line_number=idx,
                    severity="HIGH",
                    tool="pmd",
                    confidence=0.8
                ))

        return defects

    def _run_tool(self, command: List[str]) -> Optional[str]:
        joined = " ".join(command)
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=120,
                check=False
            )
        except subprocess.TimeoutExpired:
            logger.error(f"工具执行超时：{joined}")
            return None
        except FileNotFoundError:
            logger.error(f"未找到命令：{joined}")
            return None
        except Exception as e:
            logger.error(f"执行命令失败：{joined} -> {str(e)}")
            return None

        output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
        return output.strip() if output.strip() else ""

    def _parse_checkstyle_xml(self, output: str, file_path: str) -> List[Defect]:
        start = output.find("<checkstyle")
        if start == -1:
            logger.warning("未在Checkstyle输出中找到XML内容")
            return []

        try:
            root = ET.fromstring(output[start:])
        except ET.ParseError as e:
            logger.error(f"解析Checkstyle XML失败：{str(e)}")
            return []

        defects: List[Defect] = []
        # 先收集同一文件中的所有 checkstyle 报告，然后统一应用降级规则与单文件上限
        for file_elem in root.findall("file"):
            if not self._is_same_file(file_elem.get("name"), file_path):
                continue

            file_errors = []
            for error in file_elem.findall("error"):
                severity_attr = (error.get("severity") or "warning").lower()
                severity_map = {"error": "HIGH", "warning": "MEDIUM", "info": "LOW"}
                severity = severity_map.get(severity_attr, "MEDIUM")
                try:
                    line_number = int(error.get("line", -1))
                except (TypeError, ValueError):
                    line_number = -1

                cs_message = (error.get('message', '') or '').strip()
                file_errors.append((cs_message, line_number, severity))

            # 后处理规则：对 message 中多种纯格式关键词进行降级
            downgradable_tokens = [
                '制表符', 'tab', '行尾存在多余空格', '字典顺序错误', '导入组之前的额外空行',
                'whitespacearound', 'whitespace', '导入语句', '逗号后应有空格', "';' 前不应有空格",
                '注释应', '空行后应有', '名称', 'method def modifier', 'member def modifier',
                'member def type', 'method def rcurly', 'if rcurly', 'for rcurly', 'catch rcurly',
                'method def', '缩进了', '本行字符数', '行过长', '使用了制表符', '注解', '缺少 javadoc'
            ]

            # 先判断哪些错误属于需要保留为 MEDIUM 的更严重风格问题（如方法过长）
            keep_medium_if_contains = ['方法过长', '方法过长（', '方法过长（']

            # 单文件 MEDIUM 上限：避免测试/生成文件里大量重复格式性警告淹没重点
            PER_FILE_MEDIUM_CAP = 20
            medium_count = 0

            for cs_message, line_number, severity in file_errors:
                adj_severity = severity
                try:
                    msg_lower = cs_message.lower()
                    fp_lower = (file_path or '').lower()

                    # 如果是本质上的严重风格（方法过长、逻辑相关提示），保留 MEDIUM
                    if any(k.lower() in msg_lower for k in keep_medium_if_contains):
                        adj_severity = 'MEDIUM'
                    else:
                        # 对于包含在降级 token 列表中的 MEDIUM，降为 LOW
                        if adj_severity == 'MEDIUM' and any(tok in msg_lower for tok in downgradable_tokens):
                            adj_severity = 'LOW'

                        # 缺少 Javadoc：如果在测试或生成代码中，降为 LOW
                        if adj_severity == 'MEDIUM' and '缺少 javadoc' in msg_lower:
                            if any(x in fp_lower for x in ['/test/', '\\test\\', 'test/resources', 'generated_sources', 'generated']):
                                adj_severity = 'LOW'

                except Exception:
                    adj_severity = severity

                # 应用单文件 MEDIUM 上限：超过 cap 的 MEDIUM（通常是重复缩进/制表类）降为 LOW
                if adj_severity == 'MEDIUM':
                    medium_count += 1
                    if medium_count > PER_FILE_MEDIUM_CAP:
                        adj_severity = 'LOW'

                defects.append(Defect(
                    type="code_smell",
                    message=f"[checkstyle] {cs_message}",
                    line_number=line_number,
                    severity=adj_severity,
                    tool="checkstyle",
                    confidence=0.85
                ))

        return defects

    def _parse_pmd_xml(self, output: str, file_path: str) -> List[Defect]:
        start = output.find("<pmd")
        if start == -1:
            logger.warning("未在PMD输出中找到XML内容")
            return []

        try:
            root = ET.fromstring(output[start:])
        except ET.ParseError as e:
            logger.error(f"解析PMD XML失败：{str(e)}")
            return []

        defects: List[Defect] = []
        for file_elem in root.findall("file"):
            if not self._is_same_file(file_elem.get("name"), file_path):
                continue
            for violation in file_elem.findall("violation"):
                try:
                    line_number = int(violation.get("beginline", -1))
                except (TypeError, ValueError):
                    line_number = -1

                priority = violation.get("priority") or "3"
                ruleset = violation.get("ruleset", "")
                rule = violation.get("rule", "")
                message_text = (violation.text or violation.get("message") or "").strip()

                defects.append(Defect(
                    type=self._map_pmd_type(ruleset, rule, message_text),
                    message=f"[pmd] {message_text}",
                    line_number=line_number,
                    severity=self._map_pmd_priority(priority),
                    tool="pmd",
                    confidence=0.85
                ))

        return defects

    def _map_pmd_priority(self, priority: str) -> str:
        try:
            value = int(priority)
        except (TypeError, ValueError):
            return "MEDIUM"
        if value <= 1:
            return "CRITICAL"
        if value == 2:
            return "HIGH"
        if value == 3:
            return "MEDIUM"
        return "LOW"

    def _map_pmd_type(self, ruleset: str, rule: str, message: str) -> str:
        data = " ".join([ruleset or "", rule or "", message or ""]).lower()
        if "security" in data or "injection" in data or "credential" in data:
            return "security"
        if "perform" in data or "optimization" in data:
            return "performance"
        if "thread" in data or "concurrency" in data:
            return "concurrency"
        if "errorprone" in data or "bug" in data or "null" in data:
            return "logic"
        return "code_smell"

    def _is_same_file(self, reported_path: Optional[str], target_path: str) -> bool:
        if not reported_path:
            return True
        try:
            return os.path.abspath(reported_path) == os.path.abspath(target_path)
        except Exception:
            return os.path.basename(reported_path) == os.path.basename(target_path)

    def _is_tool_available(self, version_cmd: List[str]) -> bool:
        try:
            subprocess.run(
                version_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
                check=False
            )
            return True
        except FileNotFoundError:
            return False
        except subprocess.TimeoutExpired:
            logger.warning(f"检测工具版本超时：{' '.join(version_cmd)}")
            return True
        except Exception as e:
            logger.debug(f"检测工具可用性时出现异常：{str(e)}")
            return True

    def _detect_with_llm(self, file_path: str) -> List[Defect]:
        defects: List[Defect] = []
        retry_count = 0
        file_name = os.path.basename(file_path)
        is_test_file = file_name.endswith("Test.java") or file_name.startswith("Test")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code = f.read()
        except UnicodeDecodeError:
            with open(file_path, "r", encoding="latin-1") as f:
                code = f.read()
        except Exception as e:
            logger.error(f"读取Java文件{file_name}失败: {str(e)}")
            return self._get_fallback_defects(is_test_file, file_name, "文件读取失败")

        if not code:
            logger.warning(f"LLM检测失败：文件为空（{file_name}）")
            return self._get_fallback_defects(is_test_file, file_name, "文件内容为空")

        max_code_length = 4000
        if len(code) > max_code_length:
            logger.info(f"文件{file_name}过长，截断至{max_code_length}字符进行LLM检测")
            code = code[:max_code_length] + "\n...[文件内容已截断]..."

        prompt = self._build_llm_prompt(file_name, is_test_file, code)

        while retry_count < self.llm_max_retries:
            with self.llm_concurrent_semaphore:
                try:
                    logger.debug(f"向LLM发送请求检测Java文件：{file_name}（重试次数：{retry_count}）")
                    result = self._call_llm_with_timeout(prompt)

                    if result is None:
                        raise TimeoutError(f"LLM调用超时（{self.llm_request_timeout}秒）")

                    llm_response = result
                    if not llm_response or not isinstance(llm_response, str):
                        raise ValueError(f"LLM返回无效响应: {str(llm_response)[:100]}")

                    response_preview = llm_response[:500] + "..." if len(llm_response) > 500 else llm_response
                    logger.debug(f"LLM原始响应: {response_preview}")

                    llm_defects_json = self._parse_llm_response(llm_response)
                    if not isinstance(llm_defects_json, list):
                        raise ValueError(f"LLM返回的不是数组: {type(llm_defects_json)}")

                    for d in llm_defects_json:
                        valid_types = ["syntax", "security", "logic", "code_smell", "performance", "concurrency"]
                        defect_type = d.get("type", "code_smell")
                        defect_type = defect_type if defect_type in valid_types else "code_smell"

                        valid_severities = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
                        severity = d.get("severity", "MEDIUM").upper()
                        severity = severity if severity in valid_severities else "MEDIUM"

                        try:
                            line_number = int(d.get("line_number", -1))
                        except (ValueError, TypeError):
                            line_number = -1

                        defects.append(Defect(
                            type=defect_type,
                            message=f"[llm] {d.get('message', '未描述的缺陷').strip()}",
                            line_number=line_number,
                            severity=severity,
                            tool="llm",
                            confidence=0.8
                        ))

                    logger.debug(f"LLM成功检测到{len(defects)}个缺陷 in {file_name}")
                    return defects

                except (TimeoutError, ConnectionError) as e:
                    retry_count += 1
                    logger.warning(f"LLM调用超时/连接错误 (重试 {retry_count}/{self.llm_max_retries}): {str(e)}")
                    if retry_count < self.llm_max_retries:
                        sleep_time = self.llm_retry_delay * retry_count
                        logger.info(f"等待{sleep_time}秒后重试...")
                        time.sleep(sleep_time)
                    else:
                        logger.error(f"LLM调用达到最大重试次数，失败原因: {str(e)}")
                        break

                except (json.JSONDecodeError, ValueError) as e:
                    retry_count += 1
                    logger.warning(f"LLM响应解析错误 (重试 {retry_count}/{self.llm_max_retries}): {str(e)}")
                    if retry_count < self.llm_max_retries:
                        sleep_time = self.llm_retry_delay * retry_count
                        logger.info(f"等待{sleep_time}秒后重试...")
                        time.sleep(sleep_time)
                    else:
                        logger.error("LLM响应解析失败，达到最大重试次数")
                        break

                except Exception as e:
                    logger.error(f"LLM执行异常: {str(e)}", exc_info=True)
                    break

        return self._get_fallback_defects(is_test_file, file_name, "LLM服务调用失败")

    def _call_llm_with_timeout(self, prompt):
        result = [None]

        def _target():
            try:
                result[0] = deepseek_client.query(prompt, model=self.llm_model)
            except Exception as e:
                result[0] = e

        thread = threading.Thread(target=_target)
        thread.start()
        thread.join(self.llm_request_timeout)

        if thread.is_alive():
            logger.warning(f"LLM调用超时（{self.llm_request_timeout}秒）")
            return None

        if isinstance(result[0], Exception):
            raise result[0]

        return result[0]

    def _parse_llm_response(self, response):
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            json_match = re.search(r'\[\s*\{.*\}\s*\]', response, re.DOTALL)
            if not json_match:
                raise json.JSONDecodeError("无法找到有效的JSON数组", response, 0)
            return json.loads(json_match.group())

    def _build_llm_prompt(self, file_name: str, is_test_file: bool, code: str) -> str:
        return f"""
你是严格的Java代码缺陷检测专家，正在检测文件：{file_name}
{"这是一个测试文件，需要重点关注测试质量、断言和边界情况。" if is_test_file else ""}

请检测以下类型的缺陷：
- syntax: 语法错误（缺少分号、括号不匹配、未导入的类等）
- security: 安全漏洞（命令注入、SQL注入、硬编码凭据等）
- logic: 逻辑错误（空指针风险、条件判断错误、资源泄漏等）
- code_smell: 代码异味（未使用的成员、过长方法、缺少日志等）
- performance: 性能问题（字符串拼接、重复计算、集合扩容等）
- concurrency: 并发问题（未同步访问、线程安全隐患等）

【输出强制要求】：
1. 仅返回JSON数组，无任何多余文本、解释或说明
2. JSON数组中的每个元素必须包含以下字段：
   - "type"：必须是上述六种类型之一
   - "message"：详细的缺陷描述
   - "line_number"：问题所在的行号（整数）
   - "severity"：必须是CRITICAL/HIGH/MEDIUM/LOW之一
   - "tool"：固定为"llm"
   - "confidence"：固定为0.8

如果没有检测到任何缺陷，请返回空数组[]

【待检测Java代码】：
{code}
        """

    def _get_fallback_defects(self, is_test_file: bool, file_name: str, reason: str) -> List[Defect]:
        fallback_message = "建议检查测试覆盖率" if is_test_file else "建议手动复核关键逻辑"
        return [Defect(
            type="code_smell",
            message=f"[llm] 检测服务暂时不可用：{reason}，{fallback_message}",
            line_number=1,
            severity="LOW",
            tool="llm",
            confidence=0.3
        )]

    def _detect_performance_issues(self, file_path: str) -> List[Defect]:
        defects: List[Defect] = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            logger.error(f"读取Java文件失败：{str(e)}")
            return defects

        method_ranges = self._find_method_ranges(lines)
        for start, end in method_ranges:
            length = end - start + 1
            if length > self.performance_thresholds["long_method"]:
                defects.append(Defect(
                    type="performance",
                    message=f"[detector] 方法过长（{length}行），可能影响性能和可维护性",
                    line_number=start,
                    severity="MEDIUM",
                    tool="detector",
                    confidence=0.7
                ))

        loop_depth = 0
        flagged_nested_lines = set()
        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if any(keyword in stripped for keyword in ["for (", "while ("]):
                loop_depth += 1
            if loop_depth >= self.performance_thresholds["nested_loop_depth"] and idx not in flagged_nested_lines:
                defects.append(Defect(
                    type="performance",
                    message="[detector] 深层嵌套循环可能导致性能问题",
                    line_number=idx,
                    severity="MEDIUM",
                    tool="detector",
                    confidence=0.6
                ))
                flagged_nested_lines.add(idx)

            if any(loop in stripped for loop in ["for (", "while ("]):
                if re.search(r'".*"\s*\+\s*\w+', stripped):
                    concat_count = self._count_string_concat_in_block(lines, idx - 1)
                    if concat_count >= self.performance_thresholds["string_concat_threshold"]:
                        defects.append(Defect(
                            type="performance",
                            message="[detector] 循环中频繁字符串拼接，建议使用StringBuilder",
                            line_number=idx,
                            severity="MEDIUM",
                            tool="detector",
                            confidence=0.7
                        ))

            closing = stripped.count("}")
            if closing and loop_depth > 0:
                loop_depth = max(loop_depth - closing, 0)

        return defects

    def _count_string_concat_in_block(self, lines: List[str], start_index: int) -> int:
        brace_balance = 0
        concat_count = 0
        started = False
        for idx in range(start_index, len(lines)):
            line = lines[idx]
            brace_balance += line.count("{")
            brace_balance -= line.count("}")
            if re.search(r'".*"\s*\+\s*\w+', line.strip()):
                concat_count += 1
            if '{' in line:
                started = True
            if not started and idx - start_index > 20:
                break
            if started and brace_balance <= 0 and idx > start_index:
                break
        return concat_count

    def _find_method_ranges(self, lines: List[str]) -> List[tuple]:
        method_pattern = re.compile(r'(public|protected|private)\s+(static\s+)?[\w<>\[\]]+\s+\w+\s*\([^)]*\)\s*\{')
        ranges: List[tuple] = []
        idx = 0
        while idx < len(lines):
            line = lines[idx]
            if method_pattern.search(line.strip()):
                start = idx + 1
                brace_balance = line.count("{") - line.count("}")
                if brace_balance <= 0:
                    brace_balance = 1
                current = idx
                while brace_balance > 0 and current + 1 < len(lines):
                    current += 1
                    brace_balance += lines[current].count("{")
                    brace_balance -= lines[current].count("}")
                end = current + 1
                ranges.append((start, end))
                idx = current
            idx += 1
        return ranges

    def _is_empty_catch(self, lines: List[str], start_index: int) -> bool:
        brace_balance = 0
        content: List[str] = []
        for idx in range(start_index, len(lines)):
            line = lines[idx]
            brace_balance += line.count("{")
            brace_balance -= line.count("}")
            if idx > start_index:
                content.append(line.strip())
            if brace_balance <= 0 and idx > start_index:
                break
        content_text = "".join(content).replace("/*", "").replace("*/", "").strip()
        return content_text == "" or content_text == "//" or content_text.lower() in {"// todo", "// fixme"}

    def _merge_defects(self, defects_list: List[List[Defect]]) -> List[Defect]:
        merged: Dict[str, Defect] = {}
        tool_priority = {"pmd": 4, "checkstyle": 3, "llm": 2, "detector": 1}
        all_defects = [defect for sublist in defects_list for defect in sublist]

        for defect in all_defects:
            key = f"{defect.type}_{defect.line_number}_{defect.message[:50]}"
            current_priority = tool_priority.get(defect.tool, 0)
            if key not in merged or current_priority > tool_priority.get(merged[key].tool, 0):
                merged[key] = defect

        return sorted(merged.values(), key=lambda x: x.line_number)

    def _generate_severity_summary(self, file_defects_list: List[FileDefects]) -> Dict[str, int]:
        summary = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for file_defects in file_defects_list:
            for defect in file_defects.defects:
                if defect.severity in summary:
                    summary[defect.severity] += 1
        return summary

    def _generate_type_summary(self, file_defects_list: List[FileDefects]) -> Dict[str, int]:
        type_summary = {
            "syntax": 0,
            "security": 0,
            "logic": 0,
            "code_smell": 0,
            "performance": 0,
            "concurrency": 0,
        }
        for file_defects in file_defects_list:
            for defect in file_defects.defects:
                if defect.type in type_summary:
                    type_summary[defect.type] += 1
        return type_summary
