import os
import re
import json
import time
import threading
import subprocess
import logging
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
        logging.FileHandler("defect_detection_qt.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class DefectDetectorQt:
    def __init__(self):
        self.cppcheck_cmd = ["cppcheck", "--enable=all", "--output-format=json", "{file_path}"]
        self.clang_tidy_cmd = ["clang-tidy", "-checks=*", "-extra-arg=-std=c++11", "{file_path}"]
        self.llm_model = "deepseek-coder"
        self.llm_max_retries = 1
        self.llm_retry_delay = 2
        self.llm_request_timeout = 30
        self.performance_thresholds = {
            "cpp_long_function": 100,
            "cpp_file_length": 500,
            "qt_signal_slot_complexity": 10
        }
        self.max_workers = 2
        self.llm_concurrent_semaphore = threading.Semaphore(1)

    def detect(self, project_context_json: str) -> str:
        """主检测函数，接收项目上下文并返回缺陷报告"""
        try:
            logger.info("开始解析Qt项目上下文")
            project_context = ProjectContext.from_json(project_context_json)
        except Exception as e:
            logger.error(f"解析ProjectContext失败：{str(e)}")
            empty_report = DefectReport(files=[], summary={})
            return empty_report.to_json()

        defect_report = DefectReport(files=[], summary={})

        # 使用ProjectContext的cpp_files属性
        cpp_files = project_context.cpp_files

        total_files = len(cpp_files)
        logger.info(f"开始检测Qt/C++项目，共{total_files}个C++文件")
        logger.info(f"项目根目录: {project_context.project_root}")

        # 使用线程池并行处理所有文件检测
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._process_single_file, file_path): file_path
                for file_path in cpp_files
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
        file_ext = os.path.splitext(file_name)[1].lower()

        # 根据文件类型分派处理
        if file_ext in ['.cpp', '.cc', '.cxx', '.c']:
            return self._process_cpp_source_file(file_path)
        elif file_ext in ['.h', '.hpp', '.hxx']:
            return self._process_header_file(file_path)
        elif file_ext == '.ui':
            return self._process_ui_file(file_path)
        elif file_ext == '.qrc':
            return self._process_qrc_file(file_path)
        else:
            logger.warning(f"不支持的文件类型：{file_name}")
            return None

    def _process_cpp_source_file(self, file_path: str) -> FileDefects:
        """处理C++源文件检测"""
        file_name = os.path.basename(file_path)
        logger.info(f"开始C++源文件检测：{file_name}")

        # C++静态分析工具检测
        cppcheck_defects = self._detect_with_cppcheck(file_path)
        logger.info(f"[cppcheck结果] {file_name}检测到{len(cppcheck_defects)}个缺陷")

        # Qt特定规则检测
        qt_defects = self._detect_qt_specific_issues(file_path)
        logger.info(f"[Qt规则检测结果] {file_name}检测到{len(qt_defects)}个问题")

        # LLM检测
        logger.info(f"[LLM开始] 准备检测C++文件：{file_name}")
        llm_defects = self._detect_cpp_with_llm(file_path)
        logger.info(f"[LLM结果] {file_name}检测到{len(llm_defects)}个缺陷")

        # C++性能问题检测
        performance_defects = self._detect_cpp_performance_issues(file_path)
        logger.info(f"[C++性能检测结果] {file_name}检测到{len(performance_defects)}个潜在问题")

        # C++代码质量检测
        code_quality_defects = self._detect_cpp_code_quality(file_path)
        logger.info(f"[C++代码质量检测结果] {file_name}检测到{len(code_quality_defects)}个问题")

        # 合并缺陷
        merged_defects = self._merge_defects([
            cppcheck_defects,
            qt_defects,
            llm_defects,
            performance_defects,
            code_quality_defects
        ])

        if merged_defects:
            for defect in merged_defects:
                defect.file_name = file_name
            return FileDefects(file_path=file_path, defects=merged_defects)

        return None

    def _process_header_file(self, file_path: str) -> FileDefects:
        """处理头文件检测"""
        file_name = os.path.basename(file_path)
        logger.info(f"开始头文件检测：{file_name}")

        # 头文件特定检测
        header_defects = self._detect_header_specific_issues(file_path)

        # LLM检测
        llm_defects = self._detect_cpp_with_llm(file_path)

        # 合并缺陷
        merged_defects = self._merge_defects([header_defects, llm_defects])

        if merged_defects:
            for defect in merged_defects:
                defect.file_name = file_name
            return FileDefects(file_path=file_path, defects=merged_defects)

        return None

    def _process_ui_file(self, file_path: str) -> FileDefects:
        """处理UI文件检测"""
        file_name = os.path.basename(file_path)
        logger.info(f"开始UI文件检测：{file_name}")

        # UI文件特定检测
        ui_defects = self._detect_ui_specific_issues(file_path)

        if ui_defects:
            for defect in ui_defects:
                defect.file_name = file_name
            return FileDefects(file_path=file_path, defects=ui_defects)

        return None

    def _process_qrc_file(self, file_path: str) -> FileDefects:
        """处理资源文件检测"""
        file_name = os.path.basename(file_path)
        logger.info(f"开始资源文件检测：{file_name}")

        # 资源文件特定检测
        qrc_defects = self._detect_qrc_specific_issues(file_path)

        if qrc_defects:
            for defect in qrc_defects:
                defect.file_name = file_name
            return FileDefects(file_path=file_path, defects=qrc_defects)

        return None

    def _detect_with_cppcheck(self, file_path: str) -> List[Defect]:
        """使用cppcheck检测C++代码缺陷"""
        defects = []
        try:
            # 检查cppcheck是否可用
            if not self._is_tool_available("cppcheck"):
                logger.warning("cppcheck未安装，跳过C++静态分析")
                return defects

            # 使用文本输出格式
            cmd = [
                "cppcheck",
                "--enable=all",
                "--inconclusive",
                "--language=c++",
                "--suppress=missingInclude:*",  # 加通配符*，表示所有头文件的missingInclude都忽略
                file_path
            ]

            logger.debug(f"执行cppcheck命令：{' '.join(cmd)}")
            result = run_command(cmd)

            # 解析cppcheck的文本输出
            if result and isinstance(result, str):
                defects = self._parse_cppcheck_text_output(result, file_path)

            logger.info(f"cppcheck分析完成，发现{len(defects)}个缺陷")

        except Exception as e:
            logger.warning(f"cppcheck执行异常：{str(e)}")

        return defects

    def _parse_cppcheck_text_output(self, output: str, file_path: str) -> List[Defect]:
        """解析cppcheck的文本输出"""
        defects = []
        lines = output.split('\n')
        file_name = os.path.basename(file_path)

        # cppcheck输出格式模式
        pattern1 = re.compile(r'(.+?):(\d+):(\d+):\s+(\w+):\s+(.+?)\s+\[(.+?)\]')
        pattern2 = re.compile(r'(.+?):(\d+):\s+(\w+):\s+(.+)')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            match1 = pattern1.search(line)
            match2 = pattern2.search(line)

            match = match1 or match2
            if match:
                if match1:
                    filename, line_num, col_num, severity, message, error_id = match.groups()
                else:
                    filename, line_num, severity, message = match.groups()
                    error_id = "unknown"
                    col_num = "1"

                # 只处理当前文件的问题
                if filename.endswith(file_name) or file_name in filename:
                    severity_map = {
                        "error": "HIGH",
                        "warning": "MEDIUM",
                        "style": "LOW",
                        "performance": "MEDIUM",
                        "portability": "LOW",
                        "information": "LOW"
                    }

                    severity_level = severity_map.get(severity, "MEDIUM")
                    defect_type = self._map_cppcheck_type_to_defect_type(error_id)

                    try:
                        line_number = int(line_num)
                    except (ValueError, TypeError):
                        line_number = -1

                    defect = Defect(
                        type=defect_type,
                        message=f"[cppcheck] {message.strip()}",
                        line_number=line_number,
                        severity=severity_level,
                        tool="cppcheck",
                        confidence=0.85
                    )
                    defects.append(defect)

        return defects

    def _detect_qt_specific_issues(self, file_path: str) -> List[Defect]:
        """检测Qt特定问题"""
        defects = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            lines = content.split('\n')
            file_name = os.path.basename(file_path)

            # 检测内存管理问题
            for i, line in enumerate(lines):
                line_num = i + 1

                # 检测new操作没有父对象
                if re.search(r'new\s+\w+\((?!.*parent|.*this)', line) and 'QObject' in content:
                    defects.append(Defect(
                        type="memory",
                        message="[Qt] new创建的QObject对象没有设置父对象，可能导致内存泄漏",
                        line_number=line_num,
                        severity="HIGH",
                        tool="detector",
                        confidence=0.8
                    ))

                # 检测信号槽连接问题
                if 'connect(' in line and 'SIGNAL(' in line and 'SLOT(' in line:
                    if 'QObject::tr' not in line:  # 排除翻译字符串
                        defects.append(Defect(
                            type="qt_specific",
                            message="[Qt] 使用旧的字符串-based信号槽连接，建议使用新式语法",
                            line_number=line_num,
                            severity="MEDIUM",
                            tool="detector",
                            confidence=0.7
                        ))

                # 检测UI线程安全问题
                if re.search(r'QApplication::instance\(\)', line) and any(op in line for op in ['->', '.']):
                    defects.append(Defect(
                        type="concurrency",
                        message="[Qt] 可能在其他线程中访问UI对象，违反线程安全规则",
                        line_number=line_num,
                        severity="HIGH",
                        tool="detector",
                        confidence=0.75
                    ))

            logger.debug(f"Qt特定规则检测完成，{file_name}发现{len(defects)}个问题")

        except Exception as e:
            logger.error(f"Qt特定规则检测异常：{str(e)}")

        return defects

    def _detect_header_specific_issues(self, file_path: str) -> List[Defect]:
        """检测头文件特定问题"""
        defects = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            lines = content.split('\n')
            file_name = os.path.basename(file_path)

            # 检测头文件保护
            if not any(guard in content for guard in ['#ifndef', '#pragma once']):
                defects.append(Defect(
                    type="syntax",
                    message="[Header] 头文件缺少保护宏，可能导致重复包含",
                    line_number=1,
                    severity="MEDIUM",
                    tool="detector",
                    confidence=0.9
                ))

            # 检测前向声明使用
            for i, line in enumerate(lines):
                line_num = i + 1
                if '#include' in line and 'class ' in line:
                    defects.append(Defect(
                        type="code_smell",
                        message="[Header] 头文件中混用#include和前向声明，建议分离",
                        line_number=line_num,
                        severity="LOW",
                        tool="detector",
                        confidence=0.6
                    ))

        except Exception as e:
            logger.error(f"头文件检测异常：{str(e)}")

        return defects

    def _detect_ui_specific_issues(self, file_path: str) -> List[Defect]:
        """检测UI文件特定问题"""
        defects = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 检测UI文件基本问题
            if '<resources/>' in content and 'qresource' not in content:
                defects.append(Defect(
                    type="qt_specific",
                    message="[UI] UI文件中包含空的resources标签，建议移除或添加实际资源",
                    line_number=1,
                    severity="LOW",
                    tool="detector",
                    confidence=0.7
                ))

            # 检测缺少的对象名
            if re.search(r'<widget.*class="[^"]+"[^>]*>', content) and not re.search(r'name="\w+"', content):
                defects.append(Defect(
                    type="code_smell",
                    message="[UI] 存在未命名的widget对象，建议为所有widget设置objectName",
                    line_number=1,
                    severity="LOW",
                    tool="detector",
                    confidence=0.6
                ))

        except Exception as e:
            logger.error(f"UI文件检测异常：{str(e)}")

        return defects

    def _detect_qrc_specific_issues(self, file_path: str) -> List[Defect]:
        """检测资源文件特定问题"""
        defects = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 检测资源文件路径问题
            if '<file>' in content and '</file>' in content:
                file_tags = re.findall(r'<file>(.*?)</file>', content)
                for file_ref in file_tags:
                    if '..' in file_ref or file_ref.startswith('/'):
                        defects.append(Defect(
                            type="security",
                            message="[QRC] 资源文件引用包含相对路径或绝对路径，建议使用相对项目路径",
                            line_number=1,
                            severity="MEDIUM",
                            tool="detector",
                            confidence=0.7
                        ))

            # 检测空资源文件
            if not re.search(r'<file>.*</file>', content):
                defects.append(Defect(
                    type="code_smell",
                    message="[QRC] 资源文件为空或未引用任何实际文件",
                    line_number=1,
                    severity="LOW",
                    tool="detector",
                    confidence=0.8
                ))

        except Exception as e:
            logger.error(f"资源文件检测异常：{str(e)}")

        return defects

    def _detect_cpp_with_llm(self, file_path: str) -> List[Defect]:
        """使用LLM检测C++代码缺陷"""
        defects = []
        retry_count = 0
        file_name = os.path.basename(file_path)
        logger.debug(f"开始LLM检测C++文件: {file_name}")

        # 读取文件内容
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code = f.read()
        except UnicodeDecodeError:
            with open(file_path, "r", encoding="latin-1") as f:
                code = f.read()
        except Exception as e:
            logger.error(f"读取C++文件{file_name}失败: {str(e)}")
            return self._get_cpp_fallback_defects(file_name, "文件读取失败")

        if not code:
            logger.warning(f"LLM检测失败：C++文件为空（{file_name}）")
            return self._get_cpp_fallback_defects(file_name, "文件内容为空")

        # 限制代码长度
        max_code_length = 4000
        if len(code) > max_code_length:
            logger.info(f"C++文件{file_name}过长，截断至{max_code_length}字符进行LLM检测")
            code = code[:max_code_length] + "\n...[文件内容已截断]..."

        # 构建C++专用提示词
        prompt = self._build_cpp_llm_prompt(file_name, code)

        while retry_count < self.llm_max_retries:
            with self.llm_concurrent_semaphore:
                try:
                    logger.debug(f"向LLM发送请求检测C++文件：{file_name}（重试次数：{retry_count}）")
                    result = self._call_llm_with_timeout(prompt)

                    if result is None:
                        raise TimeoutError(f"LLM调用超时（{self.llm_request_timeout}秒）")

                    llm_response = result

                    if not llm_response or not isinstance(llm_response, str):
                        raise ValueError(f"LLM返回无效响应: {str(llm_response)[:100]}")

                    response_preview = llm_response[:500] + "..." if len(llm_response) > 500 else llm_response
                    logger.debug(f"LLM原始响应: {response_preview}")

                    # 解析JSON响应
                    llm_defects_json = self._parse_llm_response(llm_response)
                    if not isinstance(llm_defects_json, list):
                        raise ValueError(f"LLM返回的不是数组: {type(llm_defects_json)}")

                    # 处理解析结果
                    for d in llm_defects_json:
                        valid_types = ["syntax", "security", "logic", "code_smell", "performance", "memory",
                                       "concurrency", "qt_specific"]
                        defect_type = d.get("type", "code_smell")
                        defect_type = defect_type if defect_type in valid_types else "code_smell"

                        valid_severities = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
                        severity = d.get("severity", "MEDIUM").upper()
                        severity = severity if severity in valid_severities else "MEDIUM"

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

                    logger.debug(f"LLM成功检测到{len(defects)}个C++缺陷 in {file_name}")
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
                        logger.error(f"LLM响应解析失败，达到最大重试次数")
                        break

                except Exception as e:
                    logger.error(f"LLM执行异常: {str(e)}", exc_info=True)
                    break

        return self._get_cpp_fallback_defects(file_name, "LLM服务调用失败")

    def _call_llm_with_timeout(self, prompt):
        """带超时控制的LLM调用"""
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
        """解析LLM响应，增强容错性"""
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            json_match = re.search(r'\[\s*\{.*\}\s*\]', response, re.DOTALL)
            if not json_match:
                raise json.JSONDecodeError("无法找到有效的JSON数组", response, 0)

            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError as e:
                raise e

    def _build_cpp_llm_prompt(self, file_name, code):
        """构建C++专用LLM提示词"""
        return f"""
你是严格的C++/Qt代码缺陷检测专家，正在检测文件：{file_name}

请检测以下类型的缺陷：
- syntax: 语法错误（缺少分号、未闭合括号、类型不匹配等）
- security: 安全漏洞（缓冲区溢出、整数溢出、格式化字符串漏洞等）
- logic: 逻辑错误（资源未释放、空指针解引用、条件判断错误等）
- memory: 内存问题（内存泄漏、使用已释放内存、重复释放等）
- concurrency: 并发问题（竞态条件、死锁、原子性违反等）
- qt_specific: Qt特定问题（信号槽连接错误、内存管理问题、线程安全等）
- code_smell: 代码异味（未使用变量、重复代码、函数过长等）
- performance: 性能问题（不必要的拷贝、低效算法、大对象传值等）

特别注意Qt框架的以下问题：
1. QObject内存管理（new创建的QObject必须有父对象）
2. 信号槽连接的正确性
3. UI线程安全（避免在非UI线程操作界面）
4. 资源文件使用规范
5. 字符串编码处理

【输出强制要求】：
1. 仅返回JSON数组，无任何多余文本、解释或说明
2. JSON数组中的每个元素必须包含以下字段：
   - "type"：必须是上述八种类型之一
   - "message"：详细的缺陷描述
   - "line_number"：问题所在的行号（整数）
   - "severity"：必须是CRITICAL/HIGH/MEDIUM/LOW之一
   - "tool"：固定为"llm"
   - "confidence"：固定为0.8

如果没有检测到任何缺陷，请返回空数组[]

【待检测C++代码】：
{code}
        """

    def _get_cpp_fallback_defects(self, file_name, reason):
        """当C++ LLM调用失败时返回的备用缺陷信息"""
        return [Defect(
            type="code_smell",
            message=f"[llm] C++检测服务暂时不可用：{reason}，建议手动检查代码",
            line_number=1,
            severity="LOW",
            tool="llm",
            confidence=0.3
        )]

    def _detect_cpp_performance_issues(self, file_path: str) -> List[Defect]:
        """检测C++潜在的性能问题"""
        defects = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code = f.read()

            lines = code.split('\n')
            file_name = os.path.basename(file_path)

            # 检测大对象传值
            for i, line in enumerate(lines):
                line_num = i + 1
                if re.search(
                        r'(\w+)\s+\w+\s*\([^)]*\b(std::vector|std::string|std::map|std::set|QString|QList)[^&]*\w+\)',
                        line) and '&' not in line:
                    defects.append(Defect(
                        type="performance",
                        message="[performance] 可能的大对象传值，建议使用const引用",
                        line_number=line_num,
                        severity="MEDIUM",
                        tool="detector",
                        confidence=0.7
                    ))

                # 检测不必要的拷贝
                if re.search(r'std::vector<.*>.*=.*;', line) or re.search(r'QList<.*>.*=.*;', line):
                    defects.append(Defect(
                        type="performance",
                        message="[performance] 可能存在不必要的容器拷贝，建议使用移动语义",
                        line_number=line_num,
                        severity="MEDIUM",
                        tool="detector",
                        confidence=0.65
                    ))

                # 检测低效循环
                if re.search(r'for\s*\(.*:\s*.+\)', line) and '&' not in line and 'const' not in line:
                    defects.append(Defect(
                        type="performance",
                        message="[performance] 范围循环中可能产生不必要的拷贝，建议使用引用",
                        line_number=line_num,
                        severity="LOW",
                        tool="detector",
                        confidence=0.6
                    ))

            logger.debug(f"C++性能检测完成，{file_name}发现{len(defects)}个潜在问题")

        except Exception as e:
            logger.error(f"C++性能问题检测异常：{str(e)}")

        return defects

    def _detect_cpp_code_quality(self, file_path: str) -> List[Defect]:
        """检测C++代码质量问题"""
        defects = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code = f.read()

            lines = code.split('\n')
            file_name = os.path.basename(file_path)

            # 检测过长函数
            function_pattern = re.compile(r'(\w+)\s+\w+\s*\([^)]*\)\s*\{')
            function_starts = []

            for i, line in enumerate(lines):
                if function_pattern.search(line):
                    function_starts.append(i + 1)

            # 分析每个函数的长度
            for start_line in function_starts:
                end_line = len(lines) + 1
                for next_start in function_starts:
                    if next_start > start_line:
                        end_line = next_start - 1
                        break

                function_length = end_line - start_line
                if function_length > self.performance_thresholds["cpp_long_function"]:
                    defects.append(Defect(
                        type="code_smell",
                        message=f"[code_smell] 函数过长（{function_length}行），影响可维护性",
                        line_number=start_line,
                        severity="MEDIUM",
                        tool="detector",
                        confidence=0.7
                    ))

            # 检测文件过长
            if len(lines) > self.performance_thresholds["cpp_file_length"]:
                defects.append(Defect(
                    type="code_smell",
                    message=f"[code_smell] 文件过长（{len(lines)}行），建议拆分",
                    line_number=1,
                    severity="LOW",
                    tool="detector",
                    confidence=0.6
                ))

            # 检测使用C风格数组
            for i, line in enumerate(lines):
                line_num = i + 1
                if re.search(r'\w+\s+\w+\s*\[.*\]', line) and not re.search(r'std::array', line):
                    defects.append(Defect(
                        type="code_smell",
                        message="[code_smell] 使用C风格数组，建议使用std::array或std::vector",
                        line_number=line_num,
                        severity="LOW",
                        tool="detector",
                        confidence=0.65
                    ))

            logger.debug(f"C++代码质量检测完成，{file_name}发现{len(defects)}个问题")

        except Exception as e:
            logger.error(f"C++代码质量检测异常：{str(e)}")

        return defects

    def _is_tool_available(self, tool_name: str) -> bool:
        """检查工具是否可用"""
        try:
            if tool_name == "cppcheck":
                result = subprocess.run([tool_name, "--version"],
                                        capture_output=True, text=True, timeout=5)
                return result.returncode == 0
            return False
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            return False

    def _map_cppcheck_type_to_defect_type(self, cppcheck_id: str) -> str:
        """将cppcheck错误类型映射到标准缺陷类型"""
        type_mapping = {
            "memoryLeak": "memory",
            "resourceLeak": "memory",
            "nullPointer": "logic",
            "arrayIndexOutOfBounds": "security",
            "bufferOverflow": "security",
            "uninitvar": "logic",
            "uninitdata": "logic",
            "deadlock": "concurrency",
            "raceCondition": "concurrency",
            "invalidPrintfArg": "security"
        }
        return type_mapping.get(cppcheck_id, "code_smell")

    def _merge_defects(self, defects_list: List[List[Defect]]) -> List[Defect]:
        """合并多个工具检测到的缺陷"""
        merged_defects_map = {}
        tool_priority = {"cppcheck": 3, "llm": 2, "detector": 1}
        all_defects = [defect for sublist in defects_list for defect in sublist]

        for defect in all_defects:
            key = f"{defect.type}_{defect.line_number}_{defect.message[:50]}"

            if key not in merged_defects_map or tool_priority.get(defect.tool, 0) > tool_priority.get(
                    merged_defects_map[key].tool, 0):
                merged_defects_map[key] = defect

        return sorted(merged_defects_map.values(), key=lambda x: x.line_number)

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
            "memory": 0,
            "concurrency": 0,
            "qt_specific": 0
        }
        for file_defects in file_defects_list:
            for defect in file_defects.defects:
                if defect.type in type_summary:
                    type_summary[defect.type] += 1
        return type_summary