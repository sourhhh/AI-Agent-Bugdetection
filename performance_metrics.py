"""
Code Fixer Agent 性能评估指标
"""
from typing import List


class FixerPerformanceMetrics:
    """修复性能评估类"""

    @staticmethod
    def calculate_success_rate(test_results: List[dict]) -> float:
        """计算修复成功率"""
        successful = sum(1 for r in test_results
                         if r["strategy_used"] not in ["no_fix_applied", "error"])
        return successful / len(test_results) if test_results else 0

    @staticmethod
    def calculate_defect_reduction(original_defects: int, remaining_defects: int) -> float:
        """计算缺陷减少率"""
        return (original_defects - remaining_defects) / original_defects * 100

    @staticmethod
    def analyze_strategy_effectiveness(test_results: List[dict]) -> dict:
        """分析策略有效性"""
        strategy_stats = {}
        for result in test_results:
            strategy = result["strategy_used"]
            if strategy not in strategy_stats:
                strategy_stats[strategy] = {"count": 0, "successful": 0}

            strategy_stats[strategy]["count"] += 1
            if result.get("confidence", 0) > 0.5:
                strategy_stats[strategy]["successful"] += 1

        effectiveness = {}
        for strategy, stats in strategy_stats.items():
            effectiveness[strategy] = {
                "usage_count": stats["count"],
                "success_rate": stats["successful"] / stats["count"] if stats["count"] > 0 else 0
            }

        return effectiveness

    @staticmethod
    def generate_performance_report(test_results: List[dict], original_defects: int) -> dict:
        """生成性能报告"""
        successful_fixes = sum(1 for r in test_results
                               if r.get("confidence", 0) > 0.7)

        return {
            "total_tests": len(test_results),
            "successful_fixes": successful_fixes,
            "success_rate": successful_fixes / len(test_results) * 100,
            "defect_reduction_rate": FixerPerformanceMetrics.calculate_defect_reduction(
                original_defects, original_defects - successful_fixes
            ),
            "strategy_effectiveness": FixerPerformanceMetrics.analyze_strategy_effectiveness(test_results),
            "average_confidence": sum(r.get("confidence", 0) for r in test_results) / len(test_results)
        }
