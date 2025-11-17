# utils/report_generator.py
import os
import json
from datetime import datetime
from typing import List, Dict, Any


class RepairReportGenerator:
    """修复报告生成器"""

    def __init__(self, report_dir: str = "test_results"):
        self.report_dir = report_dir
        os.makedirs(self.report_dir, exist_ok=True)

    def generate_comprehensive_report(self, fix_results: List[Dict[str, Any]],
                                      defect_report_path: str = "") -> str:
        """生成综合修复报告"""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = os.path.join(self.report_dir, f"comprehensive_fix_report_{timestamp}.txt")

        # 生成报告内容
        report_content = self._build_report_content(fix_results, defect_report_path)

        # 写入文件
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report_content)

        return report_path

    def _build_report_content(self, fix_results: List[Dict[str, Any]], defect_report_path: str) -> str:
        """构建报告内容"""
        lines = []
        lines.append("=" * 70)
        lines.append("代码修复Agent详细修复报告")
        lines.append("=" * 70)

        # 基本信息
        if defect_report_path:
            lines.append(f"缺陷报告: {defect_report_path}")
        lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # 统计信息
        summary = self._calculate_summary(fix_results)
        lines.append(f"总修复任务: {summary['total_tasks']}")
        lines.append(f"成功修复: {summary['successful_repairs']}")
        lines.append(f"修复失败: {summary['failed_repairs']}")
        lines.append(f"修复成功率: {summary['success_rate']:.2%}")
        lines.append("")

        # 按策略统计
        lines.append("修复策略统计:")
        for strategy, stats in summary['strategy_stats'].items():
            lines.append(f"  {strategy}: {stats['success']}/{stats['total']} ({stats['success_rate']:.1%})")
        lines.append("")

        # 详细结果
        lines.append("详细修复结果:")
        lines.append("")

        for i, result in enumerate(fix_results, 1):
            lines.append(f"{i}. {result['file_path']}")
            lines.append(f"   行号: {result['line_number']}")
            lines.append(f"   缺陷类型: {result['defect_type']}")
            lines.append(f"   缺陷描述: {result['defect_message']}")
            lines.append(f"   修复策略: {result['strategy']}")
            lines.append(f"   修复状态: {'✅ 成功' if result['success'] else '❌ 失败'}")
            lines.append(f"   置信度: {result['confidence']:.2f}")
            lines.append(f"   变更内容: {', '.join(result['changes_made'])}")

            # 代码对比
            if result.get('original_code_snippet') and result.get('fixed_code_snippet'):
                lines.append("   代码对比:")
                lines.append("   [原始代码]")
                for line in result['original_code_snippet'].split('\n'):
                    lines.append(f"     {line}")
                lines.append("   [修复后代码]")
                for line in result['fixed_code_snippet'].split('\n'):
                    lines.append(f"     {line}")
            else:
                lines.append("   代码对比: 无可用代码片段")

            lines.append("")

        return '\n'.join(lines)

    def _calculate_summary(self, fix_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """计算统计信息"""
        total_tasks = len(fix_results)
        successful_repairs = sum(1 for r in fix_results if r['success'])
        failed_repairs = total_tasks - successful_repairs
        success_rate = successful_repairs / total_tasks if total_tasks > 0 else 0

        # 按策略统计
        strategy_stats = {}
        for result in fix_results:
            strategy = result['strategy']
            if strategy not in strategy_stats:
                strategy_stats[strategy] = {'total': 0, 'success': 0}
            strategy_stats[strategy]['total'] += 1
            if result['success']:
                strategy_stats[strategy]['success'] += 1

        # 计算成功率
        for strategy in strategy_stats:
            stats = strategy_stats[strategy]
            stats['success_rate'] = stats['success'] / stats['total'] if stats['total'] > 0 else 0

        return {
            'total_tasks': total_tasks,
            'successful_repairs': successful_repairs,
            'failed_repairs': failed_repairs,
            'success_rate': success_rate,
            'strategy_stats': strategy_stats
        }