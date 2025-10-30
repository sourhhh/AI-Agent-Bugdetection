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

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('cpp_repair_system.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


class CppRepairSystem:
    """C++代码修复系统 - 专门针对C++/Qt项目优化"""

    def __init__(self, max_workers: int = 2):
        self.decision_manager = DecisionManagerAgent()
        self.code_fixer = CodeFixerAgent()
        self.max_workers = max_workers
        self.processed_files = set()
        logger.info(f"C++代码修复系统初始化完成，最大工作线程: {max_workers}")

    def load_cpp_defect_report(self, report_path: str) -> DefectReport:
        """加载C++缺陷报告"""
        try:
            logger.info(f"加载C++缺陷报告: {report_path}")
            report_json = read_file(report_path)
            defect_report = DefectReport.from_json(report_json)

            # 过滤C++相关文件
            cpp_files = []
            for file_defects in defect_report.files:
                file_path = file_defects.file_path
                if self._is_cpp_file(file_path):
                    cpp_files.append(file_defects)
                    logger.info(f"包含C++文件: {file_path} - {len(file_defects.defects)}个缺陷")
                else:
                    logger.debug(f"跳过非C++文件: {file_path}")

            filtered_report = DefectReport(
                files=cpp_files,
                summary=defect_report.summary
            )

            logger.info(
                f"C++缺陷报告加载完成: {len(cpp_files)}个C++文件，共{sum(len(f.defects) for f in cpp_files)}个缺陷")
            return filtered_report

        except Exception as e:
            logger.error(f"加载C++缺陷报告失败: {str(e)}")
            raise

    def _is_cpp_file(self, file_path: str) -> bool:
        """判断是否为C++文件"""
        cpp_extensions = {'.cpp', '.cc', '.cxx', '.c++', '.h', '.hpp', '.hxx', '.hh'}
        return any(file_path.endswith(ext) for ext in cpp_extensions)

    def generate_cpp_repair_plan(self, defect_report: DefectReport) -> RepairPlan:
        """生成C++修复计划"""
        try:
            logger.info("开始生成C++修复计划...")

            start_time = time.time()
            defect_report_json = defect_report.to_json()
            repair_plan_json = self.decision_manager.analyze(defect_report_json)
            repair_plan = RepairPlan.from_json(repair_plan_json)

            execution_time = time.time() - start_time

            # 统计C++特定的修复策略
            cpp_strategies = {
                "fix_cpp_include_issues": 0,
                "fix_cpp_memory_leak": 0,
                "fix_cpp_syntax": 0,
                "fix_cpp_performance": 0,
                "fix_cpp_code_smell": 0,
                "fix_cpp_qt_specific": 0,
                "ai_automatic_fix": 0
            }

            for task in repair_plan.tasks:
                if task.strategy in cpp_strategies:
                    cpp_strategies[task.strategy] += 1

            logger.info(f"C++修复计划生成完成: {repair_plan.total_tasks}个修复任务 (耗时: {execution_time:.2f}s)")
            logger.info("C++修复策略分布:")
            for strategy, count in cpp_strategies.items():
                if count > 0:
                    logger.info(f"  {strategy}: {count}个任务")

            return repair_plan

        except Exception as e:
            logger.error(f"生成C++修复计划失败: {str(e)}")
            raise

    def execute_cpp_repairs(self, repair_plan: RepairPlan, defect_report: DefectReport) -> Dict[str, Any]:
        """执行C++修复任务"""
        try:
            logger.info(f"开始执行C++修复任务 (线程数: {self.max_workers})...")

            repair_results = []
            successful_repairs = 0
            failed_repairs = 0

            # 准备数据
            defect_report_json = defect_report.to_json()

            # 清空之前的修复结果
            self.code_fixer.clear_results()

            # 使用进度条
            with tqdm(total=repair_plan.total_tasks, desc="C++修复进度") as pbar:
                # 使用线程池但限制并发数
                with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    # 逐个提交任务
                    futures = []
                    for task in repair_plan.tasks:
                        future = executor.submit(
                            self._execute_single_cpp_repair,
                            task,
                            defect_report_json
                        )
                        futures.append(future)

                    # 处理完成的任务
                    for future in concurrent.futures.as_completed(futures):
                        try:
                            result = future.result(timeout=180)  # C++修复可能更耗时，设置3分钟超时
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
                            logger.error(f"C++任务执行异常: {str(e)}")
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
            logger.error(f"执行C++修复任务失败: {str(e)}")
            raise

    def _execute_single_cpp_repair(self, task: RepairTask, defect_report_json: str) -> Dict[str, Any]:
        """执行单个C++修复任务"""
        start_time = time.time()
        try:
            # 创建只包含当前任务的修复计划
            single_task_plan = RepairPlan(tasks=[task], total_tasks=1)
            repair_plan_json = single_task_plan.to_json()

            # 使用代码修复器执行修复
            fix_result_json = self.code_fixer.fix_code(repair_plan_json, defect_report_json)
            fix_result = FixResult.from_json(fix_result_json)

            # 从code_fixer获取最新的修复结果
            fix_results = self.code_fixer.get_fix_results()
            latest_result = fix_results[-1] if fix_results else {}

            # 使用修复器中的结果来判断成功状态
            success = latest_result.get('success', False) if latest_result else False

            if success and fix_result:
                # 保存修复后的代码
                self._save_cpp_fixed_code(fix_result)

            # 记录C++特定的调试信息
            if any(task.strategy.startswith(prefix) for prefix in ['fix_cpp_', 'ai_automatic_fix']):
                logger.debug(
                    f"执行C++修复: {task.file_path}:{task.context.get('line_number', 0)} - 策略: {task.strategy}")

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
                'fixed_code_snippet': latest_result.get('fixed_code_snippet', ''),
                'language': 'cpp'  # 标记为C++修复
            }

            return detailed_result

        except Exception as e:
            logger.error(f"执行C++修复任务失败: {str(e)}")

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
                'fixed_code_snippet': '',
                'language': 'cpp'
            }

    def _save_cpp_fixed_code(self, fix_result: FixResult):
        """保存修复后的C++代码到文件"""
        try:
            # 创建修复后的文件路径
            file_dir = os.path.dirname(fix_result.file_path)
            file_name = os.path.basename(fix_result.file_path)
            fixed_file_name = f"fixed_{file_name}"
            fixed_file_path = os.path.join(file_dir, fixed_file_name)

            # 保存修复后的代码
            write_file(fixed_file_path, fix_result.fixed_code)
            logger.debug(f"C++修复代码已保存: {fixed_file_path}")

        except Exception as e:
            logger.warning(f"保存C++修复代码失败 {fix_result.file_path}: {str(e)}")

    def generate_cpp_report(self, repair_summary: Dict[str, Any], total_time: float, defect_report_path: str):
        """生成C++修复报告"""
        # 控制台报告
        logger.info("=" * 70)
        logger.info("🔧 C++代码修复系统详细报告")
        logger.info("=" * 70)
        logger.info(f"缺陷报告: {defect_report_path}")
        logger.info(f"配置参数:")
        logger.info(f"  - 最大并行线程数: {self.max_workers}")
        logger.info(f"  - 总执行时间: {total_time:.2f}秒")
        logger.info(f"修复统计:")
        logger.info(f"  - 总修复任务: {repair_summary['total_tasks']}")
        logger.info(f"  - 成功修复: {repair_summary['successful_repairs']}")
        logger.info(f"  - 修复失败: {repair_summary['failed_repairs']}")
        logger.info(f"  - 修复成功率: {repair_summary['success_rate']:.2%}")

        # 从code_fixer获取详细的修复结果
        detailed_results = self.code_fixer.get_fix_results()

        # 生成详细报告文件
        if detailed_results:
            report_path = self._generate_cpp_text_report(detailed_results, repair_summary, total_time,
                                                         defect_report_path)
            logger.info(f"📄 C++详细修复报告已保存: {report_path}")
        else:
            logger.warning("没有可用的详细修复结果")

        # C++特定策略统计
        cpp_strategy_stats = self._calculate_cpp_strategy_stats(repair_summary['repair_results'])
        logger.info("\n🔧 C++修复策略统计:")
        for strategy, stats in cpp_strategy_stats.items():
            success_rate = stats['success'] / stats['total'] if stats['total'] > 0 else 0
            logger.info(f"  {strategy}: {stats['success']}/{stats['total']} ({success_rate:.1%})")

        # 保存JSON格式的报告
        self._save_cpp_json_report(repair_summary, detailed_results, total_time)

    def _calculate_cpp_strategy_stats(self, repair_results: List[Dict]) -> Dict:
        """计算C++策略统计"""
        cpp_strategies = {
            "fix_cpp_include_issues": {'total': 0, 'success': 0},
            "fix_cpp_memory_leak": {'total': 0, 'success': 0},
            "fix_cpp_syntax": {'total': 0, 'success': 0},
            "fix_cpp_performance": {'total': 0, 'success': 0},
            "fix_cpp_code_smell": {'total': 0, 'success': 0},
            "fix_cpp_qt_specific": {'total': 0, 'success': 0},
            "ai_automatic_fix": {'total': 0, 'success': 0}
        }

        for result in repair_results:
            strategy = result['strategy']
            if strategy in cpp_strategies:
                cpp_strategies[strategy]['total'] += 1
                if result['success']:
                    cpp_strategies[strategy]['success'] += 1

        return {k: v for k, v in cpp_strategies.items() if v['total'] > 0}

    def _generate_cpp_text_report(self, detailed_results: List[Dict], repair_summary: Dict[str, Any],
                                  total_time: float, defect_report_path: str) -> str:
        """生成C++文本报告"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = f"cpp_fix_report_{timestamp}.txt"

        report_content = []
        report_content.append("=" * 80)
        report_content.append("C++代码修复系统详细报告")
        report_content.append("=" * 80)
        report_content.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_content.append(f"缺陷报告: {defect_report_path}")
        report_content.append(f"配置参数: 线程数={self.max_workers}")
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

        # C++特定缺陷类型统计
        cpp_defect_stats = {}
        for result in detailed_results:
            defect_type = result.get('defect_type', 'unknown')
            success = result.get('success', False)

            if defect_type not in cpp_defect_stats:
                cpp_defect_stats[defect_type] = {'total': 0, 'passed': 0}
            cpp_defect_stats[defect_type]['total'] += 1
            if success:
                cpp_defect_stats[defect_type]['passed'] += 1

        report_content.append("C++缺陷类型统计:")
        for defect_type, stats in cpp_defect_stats.items():
            passed_count = stats['passed']
            total_count = stats['total']
            rate = (passed_count / total_count) * 100 if total_count > 0 else 0
            report_content.append(f"  {defect_type}: {passed_count}/{total_count} ({rate:.2f}%)")
        report_content.append("")

        # C++修复策略统计
        cpp_strategy_stats = self._calculate_cpp_strategy_stats(detailed_results)
        report_content.append("C++修复策略统计:")
        for strategy, stats in cpp_strategy_stats.items():
            passed_count = stats['success']
            total_count = stats['total']
            rate = (passed_count / total_count) * 100 if total_count > 0 else 0
            report_content.append(f"  {strategy}: {passed_count}/{total_count} ({rate:.2f}%)")
        report_content.append("")

        # 详细结果
        report_content.append("详细C++修复结果:")
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

    def _save_cpp_json_report(self, repair_summary: Dict[str, Any], detailed_results: List[Dict], total_time: float):
        """保存C++ JSON报告"""
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "configuration": {
                "max_workers": self.max_workers,
                "total_execution_time_seconds": total_time,
                "language": "cpp"
            },
            "summary": {
                "total_tasks": repair_summary['total_tasks'],
                "successful_repairs": repair_summary['successful_repairs'],
                "failed_repairs": repair_summary['failed_repairs'],
                "success_rate": repair_summary['success_rate']
            },
            "detailed_results": detailed_results,
            "cpp_specific_metrics": {
                "memory_leak_fixes": sum(1 for r in detailed_results
                                         if r['strategy'] == 'fix_cpp_memory_leak' and r['success']),
                "include_fixes": sum(1 for r in detailed_results
                                     if r['strategy'] == 'fix_cpp_include_issues' and r['success']),
                "qt_specific_fixes": sum(1 for r in detailed_results
                                         if r['strategy'] == 'fix_cpp_qt_specific' and r['success'])
            }
        }

        report_path = f"cpp_repair_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        logger.info(f"📄 C++ JSON报告已保存: {report_path}")

    def run_cpp_workflow(self, defect_report_path: str, max_tasks: int = 30):
        """运行C++工作流程"""
        logger.info("🚀 开始C++代码修复系统工作流程")
        logger.info(f"配置: 最大任务数={max_tasks}")

        # 在开始前清空修复结果
        self.code_fixer.clear_results()
        self.code_fixer.api_call_count = 0
        self.code_fixer.max_api_calls = 20  # C++修复可能需要更多API调用

        start_time = time.time()

        try:
            # 1. 加载C++缺陷报告
            defect_report = self.load_cpp_defect_report(defect_report_path)

            if not defect_report.files:
                logger.info("🎉 没有需要修复的C++缺陷，工作完成！")
                return

            # 2. 生成C++修复计划
            repair_plan = self.generate_cpp_repair_plan(defect_report)

            if repair_plan.total_tasks == 0:
                logger.info("🎉 没有需要修复的C++缺陷，工作完成！")
                return

            # 3. 限制任务数量
            if repair_plan.total_tasks > max_tasks:
                logger.warning(f"任务数量过多 ({repair_plan.total_tasks})，限制为前{max_tasks}个高优先级任务")
                repair_plan.tasks = repair_plan.tasks[:max_tasks]
                repair_plan.total_tasks = len(repair_plan.tasks)

            logger.info(f"将处理 {repair_plan.total_tasks} 个C++修复任务")

            # 4. 执行C++修复
            repair_summary = self.execute_cpp_repairs(repair_plan, defect_report)

            # 5. 生成C++报告
            total_time = time.time() - start_time
            self.generate_cpp_report(repair_summary, total_time, defect_report_path)

            logger.info("🎉 C++代码修复工作流程完成！")

        except Exception as e:
            logger.error(f"C++工作流程执行失败: {str(e)}")
            raise


def main():
    """C++修复主函数"""
    # 检查C++缺陷报告文件是否存在
    defect_report_path = "qt_project_defect_report.json"

    if not os.path.exists(defect_report_path):
        logger.error(f"C++缺陷报告文件不存在: {defect_report_path}")
        logger.info("请确保已生成C++项目的缺陷检测报告")
        return

    # C++修复配置参数 - 针对C++优化
    MAX_WORKERS = 1  # C++修复建议单线程，避免并发问题
    MAX_TASKS = 15  # 减少任务数量，提高质量

    logger.info("优化后的C++修复配置:")
    logger.info(f"  - 并行线程数: {MAX_WORKERS} (单线程确保稳定性)")
    logger.info(f"  - 最大任务数: {MAX_TASKS} (专注质量而非数量)")
    logger.info(f"  - 验证标准: 放宽C++错误关键词检测")
    logger.info(f"  - 策略选择: 优先使用专用C++修复策略")

    # 创建并运行C++修复系统
    cpp_repair_system = CppRepairSystem(max_workers=MAX_WORKERS)
    cpp_repair_system.run_cpp_workflow(defect_report_path, MAX_TASKS)


if __name__ == "__main__":
    # 安装进度条库: pip install tqdm
    main()
