import json
import logging
import os
import sys
import time
from typing import Dict, Any, List
from datetime import datetime
import concurrent.futures
from tqdm import tqdm

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agents.decision_manager import DecisionManagerAgent
from agents.code_fixer import CodeFixerAgent
from schemas.defect_report import DefectReport, FileDefects, Defect
from schemas.repair_plan import RepairPlan, RepairTask
from schemas.fix_result import FixResult
from utils.file_utils import read_file, write_file
from utils.report_generator import RepairReportGenerator  # 新增导入

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('large_scale_repair.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


class LargeScaleRepairSystem:
    """大规模代码修复系统 - 针对大量缺陷优化"""

    def __init__(self, max_workers: int = 3):
        self.decision_manager = DecisionManagerAgent()
        self.code_fixer = CodeFixerAgent()
        self.max_workers = max_workers
        self.processed_files = set()
        self.report_generator = RepairReportGenerator()  # 新增报告生成器
        self.detailed_results = []  # 新增：存储详细结果
        logger.info(f"大规模代码修复系统初始化完成，最大工作线程: {max_workers}")


    def load_and_filter_defects(self, report_path: str, min_severity: str = "LOW") -> DefectReport:
        """加载并过滤缺陷报告，只处理指定严重程度以上的缺陷"""
        try:
            logger.info(f"加载缺陷报告: {report_path}")
            report_json = read_file(report_path)
            defect_report = DefectReport.from_json(report_json)

            # 过滤缺陷
            filtered_files = []
            severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
            min_severity_level = severity_order.get(min_severity, 3)

            total_original_defects = 0
            total_filtered_defects = 0

            for file_defects in defect_report.files:
                filtered_defects = []
                for defect in file_defects.defects:
                    total_original_defects += 1
                    if severity_order.get(defect.severity, 99) <= min_severity_level:
                        filtered_defects.append(defect)
                        total_filtered_defects += 1

                if filtered_defects:
                    filtered_files.append(FileDefects(
                        file_path=file_defects.file_path,
                        defects=filtered_defects
                    ))

            filtered_report = DefectReport(
                files=filtered_files,
                summary=defect_report.summary
            )

            logger.info(f"缺陷过滤完成: 原始缺陷 {total_original_defects} -> 过滤后 {total_filtered_defects}")
            logger.info(f"处理文件数: {len(filtered_files)}")

            return filtered_report

        except Exception as e:
            logger.error(f"加载缺陷报告失败: {str(e)}")
            raise

    def generate_prioritized_repair_plan(self, defect_report: DefectReport) -> RepairPlan:
        """生成优先级修复计划"""
        try:
            logger.info("开始生成优先级修复计划...")

            start_time = time.time()
            defect_report_json = defect_report.to_json()
            repair_plan_json = self.decision_manager.analyze(defect_report_json)
            repair_plan = RepairPlan.from_json(repair_plan_json)

            execution_time = time.time() - start_time
            logger.info(f"修复计划生成完成: {repair_plan.total_tasks}个修复任务 (耗时: {execution_time:.2f}s)")

            # 按优先级统计
            priority_count = {}
            for task in repair_plan.tasks:
                priority_count[task.priority] = priority_count.get(task.priority, 0) + 1

            for priority, count in priority_count.items():
                logger.info(f"  {priority}: {count}个任务")

            return repair_plan

        except Exception as e:
            logger.error(f"生成修复计划失败: {str(e)}")
            raise

    def execute_parallel_repairs(self, repair_plan: RepairPlan, defect_report: DefectReport) -> Dict[str, Any]:
        """并行执行修复任务 - 修复版本"""
        try:
            logger.info(f"开始执行修复任务 (线程数: {self.max_workers})...")

            repair_results = []
            successful_repairs = 0
            failed_repairs = 0

            # 准备数据
            defect_report_json = defect_report.to_json()

            # 清空之前的修复结果
            self.code_fixer.clear_results()

            # 使用进度条
            with tqdm(total=repair_plan.total_tasks, desc="修复进度") as pbar:
                # 使用线程池但限制并发数
                with concurrent.futures.ThreadPoolExecutor(max_workers=min(2, self.max_workers)) as executor:
                    # 逐个提交任务，避免重复
                    futures = []
                    for task in repair_plan.tasks:
                        future = executor.submit(
                            self._execute_single_repair,
                            task,
                            defect_report_json
                        )
                        futures.append(future)

                    # 处理完成的任务
                    for future in concurrent.futures.as_completed(futures):
                        try:
                            result = future.result(timeout=120)  # 单个任务超时2分钟
                            if result:
                                repair_results.append(result)
                                if result['success']:
                                    successful_repairs += 1
                                else:
                                    failed_repairs += 1

                                pbar.update(1)
                                pbar.set_postfix({
                                    '成功': successful_repairs,
                                    '失败': failed_repairs,
                                    '成功率': f"{successful_repairs / (successful_repairs + failed_repairs):.1%}"
                                    if (successful_repairs + failed_repairs) > 0 else "0%"
                                })

                        except Exception as e:
                            logger.error(f"任务执行异常: {str(e)}")
                            failed_repairs += 1
                            pbar.update(1)

            return {
                'total_tasks': repair_plan.total_tasks,
                'successful_repairs': successful_repairs,
                'failed_repairs': failed_repairs,
                'success_rate': successful_repairs / repair_plan.total_tasks if repair_plan.total_tasks > 0 else 0,
                'repair_results': repair_results
            }
        except Exception as e:
            logger.error(f"执行修复任务失败: {str(e)}")
            raise

    def _execute_single_repair(self, task: RepairTask, defect_report_json: str) -> Dict[str, Any]:
        """执行单个修复任务 - 修复版本"""
        start_time = time.time()
        try:
            # 创建只包含当前任务的修复计划
            single_task_plan = RepairPlan(tasks=[task], total_tasks=1)
            repair_plan_json = single_task_plan.to_json()

            # 使用代码修复器执行修复
            fix_result_json = self.code_fixer.fix_code(repair_plan_json, defect_report_json)
            fix_result = FixResult.from_json(fix_result_json)

            # 从code_fixer获取最新的修复结果 - 关键修复
            fix_results = self.code_fixer.get_fix_results()
            latest_result = fix_results[-1] if fix_results else {}

            # 使用修复器中的结果来判断成功状态，而不是重新判断
            success = latest_result.get('success', False) if latest_result else False

            if success and fix_result:
                # 保存修复后的代码
                self._save_fixed_code(fix_result)

            # 特别记录AI修复的调试信息
            if task.strategy == "ai_automatic_fix":
                logger.info(f"执行AI自动修复: {task.file_path}:{task.context.get('line_number', 0)}")

            detailed_result = {
                'file_path': task.file_path,
                'defect_type': task.context.get('defect_type', 'unknown'),
                'defect_message': task.context.get('message', ''),
                'line_number': task.context.get('line_number', 0),
                'strategy': task.strategy,
                'priority': task.priority,
                'success': success,
                'confidence': latest_result.get('confidence', 0.1),
                'changes_made': latest_result.get('changes_made', ['执行失败']),
                'execution_time': time.time() - start_time,
                'original_code_snippet': latest_result.get('original_code_snippet', ''),
                'fixed_code_snippet': latest_result.get('fixed_code_snippet', '')
            }

            return detailed_result

        except Exception as e:
            logger.error(f"执行修复任务失败: {str(e)}")

            return {
                'file_path': task.file_path,
                'defect_type': task.context.get('defect_type', 'unknown'),
                'defect_message': task.context.get('message', ''),
                'line_number': task.context.get('line_number', 0),
                'strategy': task.strategy,
                'priority': task.priority,
                'success': False,
                'confidence': 0.0,
                'changes_made': [f'执行错误: {str(e)}'],
                'execution_time': time.time() - start_time,
                'original_code_snippet': '',
                'fixed_code_snippet': ''
            }

    # 在 LargeScaleRepairSystem 类中添加统一报告生成方法
    def _generate_unified_report(self, repair_summary: Dict[str, Any], total_time: float,
                                 min_severity: str, defect_report_path: str):
        """生成统一的综合报告 - 所有修复任务在一个报告中"""
        # 从code_fixer获取所有详细的修复结果
        all_fix_results = self.code_fixer.get_fix_results()

        logger.info("=" * 70)
        logger.info("📊 大规模代码修复系统统一报告")
        logger.info("=" * 70)
        logger.info(f"配置参数:")
        logger.info(f"  - 最小处理严重程度: {min_severity}")
        logger.info(f"  - 最大并行线程数: {self.max_workers}")
        logger.info(f"  - 总执行时间: {total_time:.2f}秒")
        logger.info(f"修复统计:")
        logger.info(f"  - 总修复任务: {repair_summary['total_tasks']}")
        logger.info(f"  - 成功修复: {repair_summary['successful_repairs']}")
        logger.info(f"  - 修复失败: {repair_summary['failed_repairs']}")
        logger.info(f"  - 修复成功率: {repair_summary['success_rate']:.2%}")

        # 生成统一的详细报告
        if all_fix_results:
            logger.info(f"生成统一修复报告，包含 {len(all_fix_results)} 个修复任务")
            unified_report_path = self._generate_unified_text_report(all_fix_results, repair_summary,
                                                                     total_time, min_severity, defect_report_path)
            logger.info(f"📄 统一修复报告已保存: {unified_report_path}")
        else:
            logger.warning("没有可用的修复结果")
            self._save_basic_json_report(repair_summary, total_time, min_severity)

        # 按策略统计
        strategy_stats = self._calculate_strategy_stats(all_fix_results)
        logger.info("\n🔧 修复策略统计:")
        for strategy, stats in strategy_stats.items():
            success_rate = stats['success'] / stats['total'] if stats['total'] > 0 else 0
            logger.info(f"  {strategy}: {stats['success']}/{stats['total']} ({success_rate:.1%})")

        # 保存JSON格式的统一报告
        self._save_unified_json_report(repair_summary, all_fix_results, total_time, min_severity)

    def _generate_unified_text_report(self, all_fix_results: List[Dict], repair_summary: Dict[str, Any],
                                      total_time: float, min_severity: str, defect_report_path: str) -> str:
        """生成统一的文本报告"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = f"unified_fix_report_{timestamp}.txt"

        report_content = []
        report_content.append("=" * 80)
        report_content.append("代码修复系统统一修复报告")
        report_content.append("=" * 80)
        report_content.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_content.append(f"缺陷报告: {defect_report_path}")
        report_content.append(f"配置参数: 最小严重程度={min_severity}, 线程数={self.max_workers}")
        report_content.append(f"总执行时间: {total_time:.2f}秒")
        report_content.append("")

        # 总体统计信息
        total_tasks = len(all_fix_results)
        passed_tests = sum(1 for result in all_fix_results if result.get('success', False))
        success_rate = (passed_tests / total_tasks) * 100 if total_tasks > 0 else 0

        report_content.append(f"总体统计:")
        report_content.append(f"  总修复任务: {total_tasks}")
        report_content.append(f"  成功修复: {passed_tests}")
        report_content.append(f"  修复失败: {total_tasks - passed_tests}")
        report_content.append(f"  修复成功率: {success_rate:.2f}%")
        report_content.append("")

        # 按缺陷类型统计
        defect_stats = {}
        for result in all_fix_results:
            defect_type = result.get('defect_type', 'unknown')
            success = result.get('success', False)

            if defect_type not in defect_stats:
                defect_stats[defect_type] = {'total': 0, 'passed': 0}
            defect_stats[defect_type]['total'] += 1
            if success:
                defect_stats[defect_type]['passed'] += 1

        report_content.append("按缺陷类型统计:")
        for defect_type, stats in defect_stats.items():
            passed_count = stats['passed']
            total_count = stats['total']
            rate = (passed_count / total_count) * 100 if total_count > 0 else 0
            report_content.append(f"  {defect_type}: {passed_count}/{total_count} ({rate:.2f}%)")
        report_content.append("")

        # 按修复策略统计
        strategy_stats = self._calculate_strategy_stats(all_fix_results)
        report_content.append("按修复策略统计:")
        for strategy, stats in strategy_stats.items():
            passed_count = stats['success']
            total_count = stats['total']
            rate = (passed_count / total_count) * 100 if total_count > 0 else 0
            avg_confidence = stats['confidence_sum'] / total_count if total_count > 0 else 0
            report_content.append(
                f"  {strategy}: {passed_count}/{total_count} ({rate:.2f}%), 平均置信度: {avg_confidence:.2f}")
        report_content.append("")

        # 按文件分组显示修复结果
        file_groups = {}
        for result in all_fix_results:
            file_path = result.get('file_path', '未知文件')
            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append(result)

        report_content.append("按文件分组的详细修复结果:")
        report_content.append("")

        for file_index, (file_path, file_results) in enumerate(file_groups.items(), 1):
            report_content.append(f"文件 {file_index}: {file_path}")
            report_content.append("-" * 60)

            file_success_count = sum(1 for r in file_results if r['success'])
            file_total_count = len(file_results)
            file_success_rate = (file_success_count / file_total_count) * 100 if file_total_count > 0 else 0

            report_content.append(f"  文件统计: {file_success_count}/{file_total_count} ({file_success_rate:.1f}%)")
            report_content.append("")

            for result_index, result in enumerate(file_results, 1):
                defect_type = result.get('defect_type', 'unknown')
                defect_message = result.get('defect_message', '')
                line_number = result.get('line_number', 0)
                strategy = result.get('strategy', '未知策略')
                success = result.get('success', False)
                confidence = result.get('confidence', 0)
                changes = result.get('changes_made', [])
                original_code = result.get('original_code_snippet', '')
                fixed_code = result.get('fixed_code_snippet', '')

                report_content.append(f"  {result_index}. 行号 {line_number}")
                report_content.append(f"     缺陷类型: {defect_type}")
                report_content.append(f"     缺陷描述: {defect_message}")
                report_content.append(f"     修复策略: {strategy}")
                report_content.append(f"     状态: {'✅ 成功' if success else '❌ 失败'}")
                report_content.append(f"     置信度: {confidence:.2f}")
                report_content.append(f"     变更内容: {', '.join(changes)}")

                # 代码对比 - 只在有实际变化时显示
                if (original_code and fixed_code and
                        original_code != "无变化" and fixed_code != "无变化" and
                        "无效的行号" not in original_code and "无效的行号" not in fixed_code):
                    report_content.append("     代码对比:")
                    report_content.append("     [原始代码]")
                    for line in original_code.split('\n'):
                        report_content.append(f"       {line}")
                    report_content.append("     [修复后代码]")
                    for line in fixed_code.split('\n'):
                        report_content.append(f"       {line}")
                report_content.append("")

            report_content.append("")

        # 写入文件
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(report_content))

        return report_path

    def _calculate_strategy_stats(self, all_fix_results: List[Dict]) -> Dict:
        """计算策略统计"""
        strategy_stats = {}
        for result in all_fix_results:
            strategy = result.get('strategy', 'unknown')
            success = result.get('success', False)
            confidence = result.get('confidence', 0)

            if strategy not in strategy_stats:
                strategy_stats[strategy] = {'total': 0, 'success': 0, 'confidence_sum': 0}
            strategy_stats[strategy]['total'] += 1
            strategy_stats[strategy]['confidence_sum'] += confidence
            if success:
                strategy_stats[strategy]['success'] += 1

        return strategy_stats

    def _save_unified_json_report(self, repair_summary: Dict[str, Any], all_fix_results: List[Dict],
                                  total_time: float, min_severity: str):
        """保存统一的JSON报告"""
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "configuration": {
                "min_severity": min_severity,
                "max_workers": self.max_workers,
                "total_execution_time_seconds": total_time
            },
            "summary": {
                "total_tasks": repair_summary['total_tasks'],
                "successful_repairs": repair_summary['successful_repairs'],
                "failed_repairs": repair_summary['failed_repairs'],
                "success_rate": repair_summary['success_rate']
            },
            "detailed_results": all_fix_results,
            "file_grouping": self._group_results_by_file(all_fix_results)
        }

        report_path = f"unified_repair_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        logger.info(f"📄 统一JSON报告已保存: {report_path}")

    def _group_results_by_file(self, all_fix_results: List[Dict]) -> Dict:
        """按文件分组结果"""
        file_groups = {}
        for result in all_fix_results:
            file_path = result.get('file_path', 'unknown')
            if file_path not in file_groups:
                file_groups[file_path] = {
                    'total_tasks': 0,
                    'successful_repairs': 0,
                    'failed_repairs': 0,
                    'tasks': []
                }

            file_groups[file_path]['total_tasks'] += 1
            if result.get('success', False):
                file_groups[file_path]['successful_repairs'] += 1
            else:
                file_groups[file_path]['failed_repairs'] += 1

            file_groups[file_path]['tasks'].append(result)

        return file_groups

    def _generate_comprehensive_report(self, repair_summary: Dict[str, Any], total_time: float,
                                       min_severity: str, defect_report_path: str):
        """生成综合报告 - 修复版本"""
        # 控制台报告
        logger.info("=" * 70)
        logger.info("📊 大规模代码修复系统详细报告")
        logger.info("=" * 70)
        logger.info(f"配置参数:")
        logger.info(f"  - 最小处理严重程度: {min_severity}")
        logger.info(f"  - 最大并行线程数: {self.max_workers}")
        logger.info(f"  - 总执行时间: {total_time:.2f}秒")
        logger.info(f"修复统计:")
        logger.info(f"  - 总修复任务: {repair_summary['total_tasks']}")
        logger.info(f"  - 成功修复: {repair_summary['successful_repairs']}")
        logger.info(f"  - 修复失败: {repair_summary['failed_repairs']}")
        logger.info(f"  - 修复成功率: {repair_summary['success_rate']:.2%}")

        # 从code_fixer获取详细的修复结果 - 这是关键修复
        detailed_results = self.code_fixer.get_fix_results()

        # 确保有结果时才生成详细报告
        if detailed_results:
            logger.info(f"收集到 {len(detailed_results)} 个详细修复结果")
            # 生成详细报告文件
            report_path = self._generate_detailed_text_report(detailed_results, repair_summary,
                                                              total_time, min_severity, defect_report_path)
            logger.info(f"📄 详细修复报告已保存: {report_path}")
        else:
            logger.warning("没有可用的详细修复结果，跳过详细报告生成")
            # 即使没有详细结果，也生成基础报告
            self._save_basic_json_report(repair_summary, total_time, min_severity)

        # 按策略统计
        strategy_stats = {}
        for result in repair_summary['repair_results']:
            strategy = result['strategy']
            if strategy not in strategy_stats:
                strategy_stats[strategy] = {'total': 0, 'success': 0}
            strategy_stats[strategy]['total'] += 1
            if result['success']:
                strategy_stats[strategy]['success'] += 1

        logger.info("\n🔧 修复策略统计:")
        for strategy, stats in strategy_stats.items():
            success_rate = stats['success'] / stats['total'] if stats['total'] > 0 else 0
            logger.info(f"  {strategy}: {stats['success']}/{stats['total']} ({success_rate:.1%})")

        # 保存JSON格式的报告
        self._save_json_report(repair_summary, detailed_results, total_time, min_severity)

    def _save_basic_json_report(self, repair_summary: Dict[str, Any], total_time: float, min_severity: str):
        """保存基础JSON报告（当没有详细结果时）"""
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "configuration": {
                "min_severity": min_severity,
                "max_workers": self.max_workers,
                "total_execution_time_seconds": total_time
            },
            "summary": {
                "total_tasks": repair_summary['total_tasks'],
                "successful_repairs": repair_summary['successful_repairs'],
                "failed_repairs": repair_summary['failed_repairs'],
                "success_rate": repair_summary['success_rate']
            },
            "note": "无详细修复结果可用"
        }

        report_path = f"basic_repair_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        logger.info(f"📄 基础JSON报告已保存: {report_path}")

    def _save_json_report(self, repair_summary: Dict[str, Any], detailed_results: List[Dict],
                          total_time: float, min_severity: str):
        """保存JSON格式的报告"""
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "configuration": {
                "min_severity": min_severity,
                "max_workers": self.max_workers,
                "total_execution_time_seconds": total_time
            },
            "summary": {
                "total_tasks": repair_summary['total_tasks'],
                "successful_repairs": repair_summary['successful_repairs'],
                "failed_repairs": repair_summary['failed_repairs'],
                "success_rate": repair_summary['success_rate']
            },
            "detailed_results": detailed_results
        }

        report_path = f"repair_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        logger.info(f"📄 JSON报告已保存: {report_path}")

    def _save_fixed_code(self, fix_result: FixResult):
        """保存修复后的代码到文件"""
        try:
            # 创建修复后的文件路径
            file_dir = os.path.dirname(fix_result.file_path)
            file_name = os.path.basename(fix_result.file_path)
            fixed_file_name = f"fixed_{file_name}"
            fixed_file_path = os.path.join(file_dir, fixed_file_name)

            # 保存修复后的代码
            write_file(fixed_file_path, fix_result.fixed_code)

        except Exception as e:
            logger.warning(f"保存修复代码失败 {fix_result.file_path}: {str(e)}")

    def run_batch_workflow(self, defect_report_path: str, min_severity: str = "MEDIUM", max_tasks: int = 50):
        """运行批量工作流程 - 修复版本"""
        logger.info("🚀 开始代码修复系统工作流程")
        logger.info(f"配置: 最小严重程度={min_severity}, 最大任务数={max_tasks}")

        # 在开始前清空修复结果
        self.code_fixer.clear_results()
        self.code_fixer.api_call_count = 0
        self.code_fixer.max_api_calls = 15

        start_time = time.time()

        try:
            # 1. 加载并过滤缺陷报告
            defect_report = self.load_and_filter_defects(defect_report_path, min_severity)

            if not defect_report.files:
                logger.info("🎉 没有需要修复的缺陷，工作完成！")
                return

            # 2. 生成修复计划
            repair_plan = self.generate_prioritized_repair_plan(defect_report)

            if repair_plan.total_tasks == 0:
                logger.info("🎉 没有需要修复的缺陷，工作完成！")
                return

            # 3. 限制任务数量
            if repair_plan.total_tasks > max_tasks:
                logger.warning(f"任务数量过多 ({repair_plan.total_tasks})，限制为前{max_tasks}个高优先级任务")
                repair_plan.tasks = repair_plan.tasks[:max_tasks]
                repair_plan.total_tasks = len(repair_plan.tasks)

            logger.info(f"将处理 {repair_plan.total_tasks} 个修复任务")

            # 4. 执行修复
            repair_summary = self.execute_parallel_repairs(repair_plan, defect_report)

            # 5. 生成统一的综合报告
            total_time = time.time() - start_time
            self._generate_unified_report(repair_summary, total_time, min_severity, defect_report_path)

        except Exception as e:
            logger.error(f"工作流程执行失败: {str(e)}")
            raise

    def _generate_detailed_text_report(self, detailed_results: List[Dict], repair_summary: Dict[str, Any],
                                       total_time: float, min_severity: str, defect_report_path: str) -> str:
        """生成详细的文本报告"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = f"detailed_fix_report_{timestamp}.txt"

        report_content = []
        report_content.append("=" * 80)
        report_content.append("代码修复Agent详细修复报告")
        report_content.append("=" * 80)
        report_content.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_content.append(f"缺陷报告: {defect_report_path}")
        report_content.append(f"配置参数: 最小严重程度={min_severity}, 线程数={self.max_workers}")
        report_content.append(f"总执行时间: {total_time:.2f}秒")
        report_content.append("")

        # 统计信息
        total_tasks = len(detailed_results)
        passed_tests = sum(1 for result in detailed_results if result.get('success', False))
        success_rate = (passed_tests / total_tasks) * 100 if total_tasks > 0 else 0

        report_content.append(f"总修复任务: {total_tasks}")
        report_content.append(f"成功修复: {passed_tests}")
        report_content.append(f"修复失败: {total_tasks - passed_tests}")
        report_content.append(f"修复成功率: {success_rate:.2f}%")
        report_content.append("")

        # 按缺陷类型统计
        defect_stats = {}
        for result in detailed_results:
            defect_type = result.get('defect_type', 'unknown')
            success = result.get('success', False)

            if defect_type not in defect_stats:
                defect_stats[defect_type] = {'total': 0, 'passed': 0}
            defect_stats[defect_type]['total'] += 1
            if success:
                defect_stats[defect_type]['passed'] += 1

        report_content.append("按缺陷类型统计:")
        for defect_type, stats in defect_stats.items():
            passed_count = stats['passed']
            total_count = stats['total']
            rate = (passed_count / total_count) * 100 if total_count > 0 else 0
            report_content.append(f"  {defect_type}: {passed_count}/{total_count} ({rate:.2f}%)")
        report_content.append("")

        # 按修复策略统计
        strategy_stats = {}
        for result in detailed_results:
            strategy = result.get('strategy', 'unknown')
            success = result.get('success', False)
            confidence = result.get('confidence', 0)

            if strategy not in strategy_stats:
                strategy_stats[strategy] = {'total': 0, 'passed': 0, 'confidence_sum': 0}
            strategy_stats[strategy]['total'] += 1
            strategy_stats[strategy]['confidence_sum'] += confidence
            if success:
                strategy_stats[strategy]['passed'] += 1

        report_content.append("按修复策略统计:")
        for strategy, stats in strategy_stats.items():
            passed_count = stats['passed']
            total_count = stats['total']
            rate = (passed_count / total_count) * 100 if total_count > 0 else 0
            avg_confidence = stats['confidence_sum'] / total_count if total_count > 0 else 0
            report_content.append(
                f"  {strategy}: {passed_count}/{total_count} ({rate:.2f}%), 平均置信度: {avg_confidence:.2f}")
        report_content.append("")

        # 详细结果
        report_content.append("详细修复结果:")
        report_content.append("")

        for i, result in enumerate(detailed_results, 1):
            file_path = result.get('file_path', '未知文件')
            defect_type = result.get('defect_type', 'unknown')
            defect_message = result.get('defect_message', '')
            line_number = result.get('line_number', 0)
            strategy = result.get('strategy', '未知策略')
            success = result.get('success', False)
            confidence = result.get('confidence', 0)
            changes = result.get('changes_made', [])
            original_code = result.get('original_code_snippet', '')
            fixed_code = result.get('fixed_code_snippet', '')

            report_content.append(f"{i}. {file_path}")
            report_content.append(f"   缺陷类型: {defect_type}")
            report_content.append(f"   缺陷描述: {defect_message}")
            report_content.append(f"   行号: {line_number}")
            report_content.append(f"   修复策略: {strategy}")
            report_content.append(f"   状态: {'✅ 成功' if success else '❌ 失败'}")
            report_content.append(f"   置信度: {confidence:.2f}")
            report_content.append(f"   变更内容: {', '.join(changes)}")

            # 代码对比
            if original_code and fixed_code and original_code != fixed_code:
                report_content.append("   代码对比:")
                report_content.append("   [原始代码]")
                for line in original_code.split('\n'):
                    report_content.append(f"     {line}")
                report_content.append("   [修复后代码]")
                for line in fixed_code.split('\n'):
                    report_content.append(f"     {line}")
            else:
                report_content.append("   代码对比: 无代码变化或代码片段不可用")

            report_content.append("")

        # 写入文件
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(report_content))

        return report_path

    def _save_detailed_report_file(self, repair_summary: Dict[str, Any], total_time: float, min_severity: str):
        """保存详细报告到文件"""
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "configuration": {
                "min_severity": min_severity,
                "max_workers": self.max_workers,
                "total_execution_time_seconds": total_time
            },
            "summary": {
                "total_tasks": repair_summary['total_tasks'],
                "successful_repairs": repair_summary['successful_repairs'],
                "failed_repairs": repair_summary['failed_repairs'],
                "success_rate": repair_summary['success_rate']
            },
            "detailed_results": repair_summary['repair_results']
        }

        report_path = f"repair_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        logger.info(f"📄 详细报告已保存: {report_path}")


def main():
    """主函数 - 修复版本"""
    # 检查缺陷报告文件是否存在
    defect_report_path = "requests_cache_defect_report.json"

    if not os.path.exists(defect_report_path):
        logger.error(f"缺陷报告文件不存在: {defect_report_path}")
        logger.info("请确保缺陷检测Agent已运行并生成了缺陷报告")
        return

    # 安全配置参数 - 大幅减少API调用
    MIN_SEVERITY = "HIGH"  # 只处理HIGH及以上严重程度的缺陷，减少任务数量
    MAX_WORKERS = 1        # 单线程执行，避免重复和并发问题
    MAX_TASKS = 20         # 最大任务数量，控制总费用

    logger.info(f"开始处理缺陷报告 (安全模式):")
    logger.info(f"  - 缺陷报告: {defect_report_path}")
    logger.info(f"  - 最小严重程度: {MIN_SEVERITY}")
    logger.info(f"  - 并行线程数: {MAX_WORKERS}")
    logger.info(f"  - 最大任务数: {MAX_TASKS}")

    # 创建并运行修复系统
    repair_system = LargeScaleRepairSystem(max_workers=MAX_WORKERS)
    repair_system.run_batch_workflow(defect_report_path, MIN_SEVERITY, MAX_TASKS)


if __name__ == "__main__":
    # 安装进度条库: pip install tqdm
    main()