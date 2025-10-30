import json
import os
import sys
import tempfile
import re  # 添加re模块导入
from typing import Dict, List, Any
from dataclasses import dataclass
import statistics

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.code_fixer import CodeFixerAgent
from schemas.defect_report import DefectReport, FileDefects, Defect
from schemas.repair_plan import RepairPlan, RepairTask
from schemas.fix_result import FixResult


@dataclass
class TestCase:
    """测试用例"""
    name: str
    original_code: str
    expected_fixed_code: str
    defect_type: str
    defect_message: str
    severity: str = "HIGH"
    line_number: int = 1


@dataclass
class TestResult:
    """测试结果"""
    test_case: TestCase
    success: bool
    fixed_code: str
    strategy_used: str
    changes_made: List[str]
    confidence: float
    error_message: str = ""
    actual_vs_expected: str = ""


class FixEvaluator:
    """修复评估器"""

    def __init__(self):
        self.code_fixer = CodeFixerAgent()

    def run_test(self, test_case: TestCase) -> TestResult:
        """运行单个测试用例"""
        try:
            # 创建临时文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                f.write(test_case.original_code)
                temp_file = f.name

            try:
                # 创建缺陷报告
                defect_report = DefectReport(
                    files=[
                        FileDefects(
                            file_path=temp_file,
                            defects=[
                                Defect(
                                    type=test_case.defect_type,
                                    message=test_case.defect_message,
                                    line_number=test_case.line_number,
                                    severity=test_case.severity,
                                    tool="pylint",
                                    confidence=0.9
                                )
                            ]
                        )
                    ]
                )

                # 创建修复计划
                repair_plan = RepairPlan(
                    tasks=[
                        RepairTask(
                            file_path=temp_file,
                            defect_index=0,
                            strategy=self._get_strategy_for_defect(test_case.defect_type, test_case.defect_message),
                            priority="HIGH",
                            context={
                                "defect_type": test_case.defect_type,
                                "message": test_case.defect_message,
                                "line_number": test_case.line_number
                            }
                        )
                    ],
                    total_tasks=1
                )

                # 执行修复
                fix_result_json = self.code_fixer.fix_code(
                    repair_plan.to_json(),
                    defect_report.to_json()
                )

                fix_result = FixResult.from_json(fix_result_json)

                # 评估修复结果
                success, comparison = self._evaluate_fix(test_case.expected_fixed_code, fix_result.fixed_code)

                return TestResult(
                    test_case=test_case,
                    success=success,
                    fixed_code=fix_result.fixed_code,
                    strategy_used=fix_result.strategy_used,
                    changes_made=fix_result.changes_made,
                    confidence=fix_result.confidence,
                    actual_vs_expected=comparison
                )

            finally:
                # 清理临时文件
                if os.path.exists(temp_file):
                    os.remove(temp_file)

        except Exception as e:
            import traceback
            error_details = f"{str(e)}\n{traceback.format_exc()}"
            return TestResult(
                test_case=test_case,
                success=False,
                fixed_code="",
                strategy_used="",
                changes_made=[],
                confidence=0.0,
                error_message=error_details
            )

    def _get_strategy_for_defect(self, defect_type: str, defect_message: str) -> str:
        """根据缺陷类型和消息获取修复策略"""
        message_lower = defect_message.lower()

        if defect_type == "security":
            if any(word in message_lower for word in ['eval', '代码注入']):
                return "replace_eval_with_ast_literal_eval"
            elif any(word in message_lower for word in ['pickle', '反序列化']):
                return "fix_pickle_security"
            elif any(word in message_lower for word in ['硬编码', 'password', '密码']):
                return "fix_hardcoded_secrets"
            elif any(word in message_lower for word in ['sql注入', 'sql injection']):
                return "fix_sql_injection"
            elif any(word in message_lower for word in ['命令注入', 'command injection']):
                return "fix_command_injection"
            else:
                return "ai_automatic_fix"

        elif defect_type == "logic":
            return "add_null_check"

        elif defect_type == "syntax":
            return "fix_syntax_error"

        else:
            return "ai_automatic_fix"

    def _evaluate_fix(self, expected: str, actual: str) -> tuple[bool, str]:
        """评估修复是否成功并返回比较结果 - 改进版本"""
        expected_clean = self._normalize_code(expected)
        actual_clean = self._normalize_code(actual)

        # 更宽松的比较：忽略注释、空行和细微的格式差异
        expected_lines = self._clean_comparison_lines(expected_clean)
        actual_lines = self._clean_comparison_lines(actual_clean)

        success = expected_lines == actual_lines

        comparison = f"期望:\n{expected_clean}\n\n实际:\n{actual_clean}"

        return success, comparison

    def _clean_comparison_lines(self, code: str) -> list[str]:
        """清理代码行用于比较"""
        lines = []
        for line in code.split('\n'):
            line = line.strip()
            # 跳过空行和纯注释行
            if line and not line.startswith('#') and not line.startswith('"""'):
                # 移除多余的空格
                line = re.sub(r'\s+', ' ', line)
                lines.append(line)
        return lines

    def _normalize_code(self, code: str) -> str:
        """标准化代码用于比较 - 改进版本"""
        if not code:
            return ""

        # 移除空行和前后空格，但保留基本结构
        lines = []
        for line in code.split('\n'):
            stripped = line.strip()
            if stripped:  # 只保留非空行
                lines.append(stripped)

        return '\n'.join(lines)

    def run_test_suite(self, test_cases: List[TestCase]) -> Dict[str, Any]:
        """运行测试套件"""
        results = []

        for test_case in test_cases:
            print(f"运行测试: {test_case.name}")
            result = self.run_test(test_case)
            results.append(result)

            status = "✓ 通过" if result.success else "✗ 失败"
            print(f"  {status} - 策略: {result.strategy_used}, 置信度: {result.confidence:.2f}")

            if not result.success:
                print(f"  修复变更: {result.changes_made}")
                if result.error_message:
                    error_first_line = result.error_message.split('\n')[0]
                    print(f"  错误: {error_first_line}")

        # 计算统计信息
        return self._calculate_statistics(results)

    def _calculate_statistics(self, results: List[TestResult]) -> Dict[str, Any]:
        """计算测试统计信息"""
        total_tests = len(results)
        passed_tests = sum(1 for r in results if r.success)
        success_rate = passed_tests / total_tests if total_tests > 0 else 0

        # 按缺陷类型统计
        type_stats = {}
        for result in results:
            defect_type = result.test_case.defect_type
            if defect_type not in type_stats:
                type_stats[defect_type] = {"total": 0, "passed": 0}
            type_stats[defect_type]["total"] += 1
            if result.success:
                type_stats[defect_type]["passed"] += 1

        # 按策略统计
        strategy_stats = {}
        for result in results:
            strategy = result.strategy_used
            if strategy not in strategy_stats:
                strategy_stats[strategy] = {"total": 0, "passed": 0, "confidence": []}
            strategy_stats[strategy]["total"] += 1
            if result.success:
                strategy_stats[strategy]["passed"] += 1
            strategy_stats[strategy]["confidence"].append(result.confidence)

        # 计算平均置信度
        for strategy in strategy_stats:
            confidences = strategy_stats[strategy]["confidence"]
            strategy_stats[strategy]["avg_confidence"] = statistics.mean(confidences) if confidences else 0

        return {
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "success_rate": success_rate,
            "type_statistics": type_stats,
            "strategy_statistics": strategy_stats,
            "detailed_results": results
        }

    def generate_report(self, test_results: Dict[str, Any]) -> str:
        """生成测试报告"""
        report = []
        report.append("=" * 60)
        report.append("代码修复Agent测试报告")
        report.append("=" * 60)
        report.append(f"总测试数: {test_results['total_tests']}")
        report.append(f"通过数: {test_results['passed_tests']}")
        report.append(f"成功率: {test_results['success_rate']:.2%}")
        report.append("")

        # 按缺陷类型统计
        report.append("按缺陷类型统计:")
        for defect_type, stats in test_results['type_statistics'].items():
            rate = stats['passed'] / stats['total'] if stats['total'] > 0 else 0
            report.append(f"  {defect_type}: {stats['passed']}/{stats['total']} ({rate:.2%})")

        report.append("")

        # 按策略统计
        report.append("按修复策略统计:")
        for strategy, stats in test_results['strategy_statistics'].items():
            rate = stats['passed'] / stats['total'] if stats['total'] > 0 else 0
            report.append(
                f"  {strategy}: {stats['passed']}/{stats['total']} ({rate:.2%}), 平均置信度: {stats['avg_confidence']:.2f}")

        return '\n'.join(report)

    def generate_detailed_report(self, test_results: Dict[str, Any]) -> str:
        """生成详细报告"""
        report = [self.generate_report(test_results)]
        report.append("\n详细结果:")

        for i, result in enumerate(test_results['detailed_results']):
            report.append(f"\n{i + 1}. {result.test_case.name}")
            report.append(f"   状态: {'通过' if result.success else '失败'}")
            report.append(f"   策略: {result.strategy_used}")
            report.append(f"   置信度: {result.confidence:.2f}")
            report.append(f"   变更: {result.changes_made}")

            if not result.success:
                report.append(f"   代码比较:\n{result.actual_vs_expected}")
                if result.error_message:
                    error_first_line = result.error_message.split('\n')[0]
                    report.append(f"   错误: {error_first_line}")

        return '\n'.join(report)
