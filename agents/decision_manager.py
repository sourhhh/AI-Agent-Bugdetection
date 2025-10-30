import logging
import json
from typing import List, Dict, Literal
import concurrent.futures

from config import Config
from utils.ai_analyzer import ai_analyzer  # 使用专门的AI分析器
from schemas.defect_report import DefectReport, Defect
from schemas.repair_plan import RepairPlan, RepairTask

logger = logging.getLogger(__name__)


class DecisionManagerAgent:
    """决策管理器Agent - 优化版本"""

    def __init__(self):
        logger.info("初始化DecisionManagerAgent...")

        # 使用专门的AI分析器
        self.ai_analyzer = ai_analyzer

        # 添加缓存机制
        self.priority_cache = {}  # 缺陷消息 -> 优先级缓存
        self.strategy_cache = {}  # 缺陷特征 -> 策略缓存

        if not self.ai_analyzer.is_available():
            logger.warning("AI分析引擎不可用，将使用默认规则")

    def analyze(self, defect_report_json: str) -> str:
        """
        主分析方法：接收缺陷报告JSON，返回修复计划JSON
        """
        try:
            logger.info("开始分析缺陷报告...")

            # 1. 解析输入JSON
            defect_report = DefectReport.from_json(defect_report_json)
            logger.info(f"解析成功，共发现 {len(defect_report.files)} 个文件有缺陷")

            # 2. 生成修复计划
            repair_plan = self._generate_repair_plan_optimized(defect_report)

            # 3. 返回JSON结果
            result_json = repair_plan.to_json()
            logger.info(f"分析完成，生成 {repair_plan.total_tasks} 个修复任务")

            return result_json

        except Exception as e:
            logger.error(f"分析缺陷报告失败: {str(e)}")
            empty_plan = RepairPlan(tasks=[], total_tasks=0)
            return empty_plan.to_json()

    def _generate_repair_plan_optimized(self, defect_report: DefectReport) -> RepairPlan:
        """优化版本：批量+缓存+并行处理"""
        repair_tasks = []
        all_defects = []

        # 收集所有缺陷
        total_defects = 0
        for file_defects in defect_report.files:
            for defect_index, defect in enumerate(file_defects.defects):
                all_defects.append((file_defects.file_path, defect_index, defect))
                total_defects += 1

        logger.info(f"共收集到 {total_defects} 个缺陷，开始批量处理...")

        # 批量处理缺陷
        if total_defects > 50:
            # 大量缺陷使用并行处理
            repair_tasks = self._process_defects_parallel(all_defects)
        else:
            # 少量缺陷使用串行处理
            repair_tasks = self._process_defects_sequential(all_defects)

        # 按优先级排序
        repair_tasks.sort(key=lambda x: self._get_priority_value(x.priority))
        logger.info(f"修复任务排序完成，最高优先级: {repair_tasks[0].priority if repair_tasks else '无'}")

        return RepairPlan(tasks=repair_tasks, total_tasks=len(repair_tasks))

    def _process_defects_sequential(self, all_defects: List[tuple]) -> List[RepairTask]:
        """串行处理缺陷"""
        repair_tasks = []

        for file_path, defect_index, defect in all_defects:
            try:
                # 使用缓存获取优先级
                priority = self._get_cached_priority(defect)
                strategy = self._select_repair_strategy_fast(defect, file_path)

                task = RepairTask(
                    file_path=file_path,
                    defect_index=defect_index,
                    strategy=strategy,
                    priority=priority,
                    context={
                        "defect_type": defect.type,
                        "message": defect.message,
                        "line_number": defect.line_number,
                        "severity": defect.severity
                    }
                )
                repair_tasks.append(task)

            except Exception as e:
                logger.error(f"处理缺陷失败 {file_path}:{defect.line_number} - {str(e)}")
                continue

        return repair_tasks

    def _process_defects_parallel(self, all_defects: List[tuple]) -> List[RepairTask]:
        """并行处理缺陷"""
        repair_tasks = []

        # 使用线程池并行处理
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_to_defect = {}

            # 提交所有任务
            for defect_data in all_defects:
                future = executor.submit(self._process_single_defect, defect_data)
                future_to_defect[future] = defect_data

            # 收集结果
            for future in concurrent.futures.as_completed(future_to_defect):
                try:
                    task = future.result(timeout=30)  # 30秒超时
                    if task:
                        repair_tasks.append(task)
                except Exception as e:
                    defect_data = future_to_defect[future]
                    file_path, defect_index, defect = defect_data
                    logger.error(f"并行处理缺陷失败 {file_path}:{defect.line_number} - {str(e)}")

        return repair_tasks

    def _process_single_defect(self, defect_data: tuple) -> RepairTask:
        """处理单个缺陷（用于并行处理）"""
        file_path, defect_index, defect = defect_data

        # 使用缓存获取优先级
        priority = self._get_cached_priority(defect)
        strategy = self._select_repair_strategy_fast(defect, file_path)

        return RepairTask(
            file_path=file_path,
            defect_index=defect_index,
            strategy=strategy,
            priority=priority,
            context={
                "defect_type": defect.type,
                "message": defect.message,
                "line_number": defect.line_number,
                "severity": defect.severity
            }
        )

    def _get_cached_priority(self, defect: Defect) -> str:
        """获取缓存的优先级"""
        cache_key = f"{defect.type}:{defect.severity}:{defect.message[:100]}"

        if cache_key in self.priority_cache:
            return self.priority_cache[cache_key]

        # 如果AI分析器可用，使用AI分析优先级
        if self.ai_analyzer.is_available():
            try:
                priority = self.ai_analyzer.analyze_defect_priority(
                    defect.type, defect.message, defect.severity, defect.line_number
                )
            except Exception as e:
                logger.warning(f"AI分析优先级失败，使用规则分析: {str(e)}")
                priority = self._rule_based_priority(defect)
        else:
            # 使用规则分析
            priority = self._rule_based_priority(defect)

        self.priority_cache[cache_key] = priority
        return priority

    def _rule_based_priority(self, defect: Defect) -> str:
        """基于规则的优先级分析"""
        # 严重程度直接映射
        severity_map = {
            "CRITICAL": "CRITICAL",
            "HIGH": "HIGH",
            "MEDIUM": "MEDIUM",
            "LOW": "LOW"
        }

        # 安全缺陷提升优先级
        if defect.type == "security":
            if defect.severity == "MEDIUM":
                return "HIGH"
            elif defect.severity == "LOW":
                return "MEDIUM"

        return severity_map.get(defect.severity, "MEDIUM")

    def _select_repair_strategy_fast(self, defect: Defect, file_path: str = "") -> str:
        """快速策略选择 - 减少AI调用"""
        # 检测文件类型
        is_cpp_file = file_path.endswith(('.cpp', '.cc', '.cxx', '.h', '.hpp'))

        if is_cpp_file:
            return self._select_cpp_repair_strategy_fast(defect)
        else:
            return self._select_python_repair_strategy_fast(defect)

    def _select_cpp_repair_strategy_fast(self, defect: Defect) -> str:
        """快速C++策略选择"""
        message_lower = defect.message.lower()

        # 基于关键词的快速匹配
        keyword_strategy_map = {
            'memory': 'fix_cpp_memory_leak',
            '内存泄漏': 'fix_cpp_memory_leak',
            '内存泄露': 'fix_cpp_memory_leak',
            'include': 'fix_cpp_include_issues',
            '头文件': 'fix_cpp_include_issues',
            '未找到': 'fix_cpp_include_issues',
            'qt': 'fix_cpp_qt_specific',
            'qsql': 'fix_cpp_qt_specific',
            'qobject': 'fix_cpp_qt_specific',
            '数据库连接': 'fix_cpp_qt_specific',
            'performance': 'fix_cpp_performance',
            '性能': 'fix_cpp_performance',
            '拷贝': 'fix_cpp_performance',
            '引用': 'fix_cpp_performance',
            '范围循环': 'fix_cpp_performance',
            'syntax': 'fix_cpp_syntax',
            '语法': 'fix_cpp_syntax',
            '缺少分号': 'fix_cpp_syntax',
            '作用域': 'fix_cpp_syntax',
            'code_smell': 'fix_cpp_code_smell',
            '代码异味': 'fix_cpp_code_smell',
            '文件过长': 'fix_cpp_code_smell',
            '函数过长': 'fix_cpp_code_smell'
        }

        for keyword, strategy in keyword_strategy_map.items():
            if keyword in message_lower:
                return strategy

        # 默认使用AI修复
        return "ai_automatic_fix"

    def _select_python_repair_strategy_fast(self, defect: Defect) -> str:
        """快速Python策略选择"""
        message_lower = defect.message.lower()

        # 安全缺陷使用专用策略
        if defect.type == "security":
            return self._select_security_repair_strategy_fast(defect)

        # 基于缺陷类型的快速选择
        type_strategy_map = {
            "syntax": "fix_syntax_error",
            "logic": "add_null_check",
            "performance": "ai_automatic_fix",
            "code_smell": "ai_automatic_fix"
        }

        # 特定关键词覆盖
        if "indent" in message_lower or "indentation" in message_lower:
            return "fix_indentation"
        elif "eval" in message_lower:
            return "replace_eval_with_ast_literal_eval"
        elif "pickle" in message_lower:
            return "fix_pickle_security"
        elif "hardcoded" in message_lower or "密码" in message_lower:
            return "fix_hardcoded_secrets"
        elif "sql" in message_lower and "injection" in message_lower:
            return "fix_sql_injection"

        return type_strategy_map.get(defect.type, "ai_automatic_fix")

    def _select_security_repair_strategy_fast(self, defect: Defect) -> str:
        """快速安全策略选择"""
        message_lower = defect.message.lower()

        security_strategy_map = {
            'eval': 'replace_eval_with_ast_literal_eval',
            '代码注入': 'replace_eval_with_ast_literal_eval',
            'pickle': 'fix_pickle_security',
            '反序列化': 'fix_pickle_security',
            'deserialization': 'fix_pickle_security',
            '硬编码': 'fix_hardcoded_secrets',
            'hardcoded': 'fix_hardcoded_secrets',
            'password': 'fix_hardcoded_secrets',
            '密码': 'fix_hardcoded_secrets',
            '密钥': 'fix_hardcoded_secrets',
            'sql注入': 'fix_sql_injection',
            'sql injection': 'fix_sql_injection',
            '字符串格式化': 'fix_sql_injection',
            '命令注入': 'fix_command_injection',
            'command injection': 'fix_command_injection',
            'os.popen': 'fix_command_injection',
            'subprocess': 'fix_command_injection'
        }

        for keyword, strategy in security_strategy_map.items():
            if keyword in message_lower:
                return strategy

        return "ai_automatic_fix"

    def _get_priority_value(self, priority: str) -> int:
        """获取优先级数值用于排序"""
        priority_map = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        return priority_map.get(priority, 99)

    def _batch_rule_based_priority(self, all_defects: List[tuple]) -> List[str]:
        """批量基于规则的优先级分析"""
        priorities = []
        for file_path, defect_index, defect in all_defects:
            priorities.append(self._rule_based_priority(defect))
        return priorities

    # 保留原有方法用于兼容性
    def _select_logic_repair_strategy(self, defect: Defect) -> str:
        """选择逻辑错误修复策略"""
        return "add_null_check"

    def _select_syntax_repair_strategy(self, defect: Defect) -> str:
        """选择语法错误修复策略"""
        message_lower = defect.message.lower()
        if any(word in message_lower for word in ['缩进', 'indentation']):
            return "fix_indentation"
        return "fix_syntax_error"

    def _select_security_repair_strategy(self, defect: Defect) -> str:
        """根据安全缺陷信息选择修复策略"""
        return self._select_security_repair_strategy_fast(defect)

    def _select_repair_strategy(self, defect: Defect, file_path: str = "") -> str:
        """原有策略选择方法"""
        return self._select_repair_strategy_fast(defect, file_path)

    def _select_cpp_repair_strategy(self, defect: Defect) -> str:
        """原有C++策略选择方法"""
        return self._select_cpp_repair_strategy_fast(defect)

    def _select_python_repair_strategy(self, defect: Defect) -> str:
        """原有Python策略选择方法"""
        return self._select_python_repair_strategy_fast(defect)

    def process_file(self, input_file: str, output_file: str) -> bool:
        """
        文件处理接口：从文件读取缺陷报告，生成修复计划文件
        """
        try:
            logger.info(f"处理文件: {input_file} -> {output_file}")

            with open(input_file, 'r', encoding='utf-8') as f:
                defect_report_json = f.read()

            repair_plan_json = self.analyze(defect_report_json)

            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(repair_plan_json)

            logger.info(f"修复计划已保存: {output_file}")
            return True

        except Exception as e:
            logger.error(f"文件处理失败: {str(e)}")
            return False