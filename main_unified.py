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
        logging.FileHandler('unified_repair_system.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


class UnifiedRepairSystem:
    """统一代码修复系统 - 支持Python和C++项目（修复版本）"""

    def __init__(self, max_workers: int = 2):
        self.decision_manager = DecisionManagerAgent()
        self.code_fixer = CodeFixerAgent()
        self.max_workers = max_workers
        self.processed_files = set()
        logger.info(f"统一代码修复系统初始化完成，最大工作线程: {max_workers}")

    def detect_project_language(self, project_path: str) -> Dict[str, Any]:
        """检测项目的主要编程语言"""
        logger.info(f"检测项目语言: {project_path}")

        language_stats = {
            "python": {"files": 0, "extensions": ['.py', '.pyw']},
            "cpp": {"files": 0, "extensions": ['.cpp', '.cc', '.cxx', '.c++', '.h', '.hpp', '.hxx', '.hh']},
            "other": {"files": 0}
        }

        try:
            for root, dirs, files in os.walk(project_path):
                # 跳过虚拟环境目录
                if any(skip_dir in root for skip_dir in
                       ['venv', '.venv', 'env', '__pycache__', 'node_modules', '.git']):
                    continue

                for file in files:
                    file_path = os.path.join(root, file)
                    file_ext = os.path.splitext(file)[1].lower()

                    # 分类文件类型
                    if file_ext in language_stats["python"]["extensions"]:
                        language_stats["python"]["files"] += 1
                    elif file_ext in language_stats["cpp"]["extensions"]:
                        language_stats["cpp"]["files"] += 1
                    else:
                        language_stats["other"]["files"] += 1

            # 确定主要语言
            python_files = language_stats["python"]["files"]
            cpp_files = language_stats["cpp"]["files"]

            if python_files > cpp_files and python_files > 0:
                primary_language = "python"
            elif cpp_files > python_files and cpp_files > 0:
                primary_language = "cpp"
            elif python_files > 0 and cpp_files > 0:
                primary_language = "mixed"  # 混合项目
            else:
                primary_language = "unknown"

            language_stats["primary_language"] = primary_language
            language_stats["total_code_files"] = python_files + cpp_files

            logger.info(f"项目语言检测结果: {primary_language}")
            logger.info(
                f"Python文件: {python_files}, C++文件: {cpp_files}, 其他文件: {language_stats['other']['files']}")

            return language_stats

        except Exception as e:
            logger.error(f"检测项目语言失败: {str(e)}")
            return {"primary_language": "unknown", "total_code_files": 0}

    def load_defect_report(self, report_path: str, target_language: str = "auto",
                           min_severity: str = "LOW") -> DefectReport:
        """加载缺陷报告，支持语言和严重程度过滤 - 修复版本"""
        try:
            logger.info(f"加载缺陷报告: {report_path}")
            report_json = read_file(report_path)
            defect_report = DefectReport.from_json(report_json)

            # 严重程度过滤（新增关键修复）
            severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
            min_severity_level = severity_order.get(min_severity, 3)

            filtered_files = []
            total_original_defects = 0
            total_filtered_defects = 0

            for file_defects in defect_report.files:
                # 首先进行严重程度过滤
                filtered_defects = []
                for defect in file_defects.defects:
                    total_original_defects += 1
                    if severity_order.get(defect.severity, 99) <= min_severity_level:
                        filtered_defects.append(defect)
                        total_filtered_defects += 1

                if not filtered_defects:
                    continue

                file_path = file_defects.file_path

                # 然后进行语言过滤
                if target_language == "auto":
                    # 自动检测文件语言 - 使用增强版本
                    file_language = self._detect_file_language_enhanced(file_path)
                    if file_language in ["python", "cpp"]:
                        filtered_files.append(FileDefects(
                            file_path=file_path,
                            defects=filtered_defects
                        ))
                        logger.debug(f"包含文件: {file_path} - 语言: {file_language} - {len(filtered_defects)}个缺陷")
                elif target_language == "python":
                    if self._is_python_file(file_path):
                        filtered_files.append(FileDefects(
                            file_path=file_path,
                            defects=filtered_defects
                        ))
                elif target_language == "cpp":
                    if self._is_cpp_file(file_path):
                        filtered_files.append(FileDefects(
                            file_path=file_path,
                            defects=filtered_defects
                        ))
                else:
                    # 不进行语言过滤
                    filtered_files.append(FileDefects(
                        file_path=file_path,
                        defects=filtered_defects
                    ))

            filtered_report = DefectReport(
                files=filtered_files,
                summary=defect_report.summary
            )

            logger.info(f"缺陷报告加载完成: {len(filtered_files)}个文件")
            logger.info(f"缺陷过滤统计: 原始缺陷 {total_original_defects} -> 过滤后 {total_filtered_defects}")
            logger.info(f"最小严重程度: {min_severity}")

            return filtered_report

        except Exception as e:
            logger.error(f"加载缺陷报告失败: {str(e)}")
            raise

    def _detect_file_language_enhanced(self, file_path: str) -> str:
        """增强版语言检测 - 修复关键问题"""
        # 优先通过文件扩展名检测
        if self._is_python_file(file_path):
            return "python"
        elif self._is_cpp_file(file_path):
            return "cpp"

        # 备用方案：尝试读取文件内容检测
        try:
            if os.path.exists(file_path):
                content = read_file(file_path)
                # Python特征检测
                python_keywords = ['def ', 'import ', 'from ', 'class ', 'print(', 'if __name__', 'lambda ']
                cpp_keywords = ['#include', 'using namespace', 'class ', 'struct ', 'public:', 'private:', 'cout <<',
                                'endl;']

                python_count = sum(1 for keyword in python_keywords if keyword in content)
                cpp_count = sum(1 for keyword in cpp_keywords if keyword in content)

                if python_count > cpp_count and python_count > 0:
                    return "python"
                elif cpp_count > python_count and cpp_count > 0:
                    return "cpp"
        except Exception as e:
            logger.debug(f"文件内容检测失败 {file_path}: {str(e)}")

        # 默认根据文件路径判断
        if any(ext in file_path for ext in ['.py', '.pyw']):
            return "python"
        elif any(ext in file_path for ext in ['.cpp', '.cc', '.cxx', '.h', '.hpp']):
            return "cpp"
        else:
            return "other"

    def _detect_file_language(self, file_path: str) -> str:
        """保持原有方法兼容性"""
        return self._detect_file_language_enhanced(file_path)

    def _is_python_file(self, file_path: str) -> bool:
        """判断是否为Python文件"""
        python_extensions = {'.py', '.pyw'}
        return any(file_path.endswith(ext) for ext in python_extensions)

    def _is_cpp_file(self, file_path: str) -> bool:
        """判断是否为C++文件"""
        cpp_extensions = {'.cpp', '.cc', '.cxx', '.c++', '.h', '.hpp', '.hxx', '.hh'}
        return any(file_path.endswith(ext) for ext in cpp_extensions)

    def generate_repair_plan(self, defect_report: DefectReport, language: str = "auto") -> RepairPlan:
        """生成修复计划"""
        try:
            logger.info(f"开始生成修复计划... (语言: {language})")

            start_time = time.time()
            defect_report_json = defect_report.to_json()
            repair_plan_json = self.decision_manager.analyze(defect_report_json)
            repair_plan = RepairPlan.from_json(repair_plan_json)

            execution_time = time.time() - start_time

            # 统计修复策略分布
            strategy_stats = {}
            for task in repair_plan.tasks:
                strategy = task.strategy
                strategy_stats[strategy] = strategy_stats.get(strategy, 0) + 1

            logger.info(f"修复计划生成完成: {repair_plan.total_tasks}个修复任务 (耗时: {execution_time:.2f}s)")
            logger.info("修复策略分布:")
            for strategy, count in strategy_stats.items():
                logger.info(f"  {strategy}: {count}个任务")

            return repair_plan

        except Exception as e:
            logger.error(f"生成修复计划失败: {str(e)}")
            raise

    def execute_repairs(self, repair_plan: RepairPlan, defect_report: DefectReport) -> Dict[str, Any]:
        """执行修复任务 - 优化版本"""
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
                with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    # 逐个提交任务
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
        """执行单个修复任务"""
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
                self._save_fixed_code(fix_result)

            # 检测文件语言用于报告
            file_language = self._detect_file_language(task.file_path)

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
                'language': file_language
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
                'fixed_code_snippet': '',
                'language': self._detect_file_language(task.file_path)
            }

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
            logger.debug(f"修复代码已保存: {fixed_file_path}")

        except Exception as e:
            logger.warning(f"保存修复代码失败 {fix_result.file_path}: {str(e)}")

    def generate_comprehensive_report(self, repair_summary: Dict[str, Any], total_time: float,
                                      project_path: str, defect_report_path: str, language: str, min_severity: str):
        """生成综合报告 - 修复版本"""
        # 控制台报告
        logger.info("=" * 70)
        logger.info("🚀 统一代码修复系统详细报告")
        logger.info("=" * 70)
        logger.info(f"项目路径: {project_path}")
        logger.info(f"缺陷报告: {defect_report_path}")
        logger.info(f"目标语言: {language}")
        logger.info(f"最小严重程度: {min_severity}")  # 新增
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
            report_path = self._generate_unified_text_report(detailed_results, repair_summary,
                                                             total_time, project_path, defect_report_path, language,
                                                             min_severity)
            logger.info(f"📄 详细修复报告已保存: {report_path}")
        else:
            logger.warning("没有可用的详细修复结果")

        # 按语言和策略统计
        language_stats = self._calculate_language_stats(repair_summary['repair_results'])
        strategy_stats = self._calculate_strategy_stats(repair_summary['repair_results'])

        logger.info("\n🔧 按语言统计:")
        for lang, stats in language_stats.items():
            success_rate = stats['success'] / stats['total'] if stats['total'] > 0 else 0
            logger.info(f"  {lang}: {stats['success']}/{stats['total']} ({success_rate:.1%})")

        logger.info("\n🔧 修复策略统计:")
        for strategy, stats in strategy_stats.items():
            success_rate = stats['success'] / stats['total'] if stats['total'] > 0 else 0
            logger.info(f"  {strategy}: {stats['success']}/{stats['total']} ({success_rate:.1%})")

        # 保存JSON格式的报告
        self._save_unified_json_report(repair_summary, detailed_results, total_time,
                                       project_path, defect_report_path, language, min_severity)

    def _calculate_language_stats(self, repair_results: List[Dict]) -> Dict:
        """计算语言统计"""
        language_stats = {}
        for result in repair_results:
            language = result.get('language', 'unknown')
            if language not in language_stats:
                language_stats[language] = {'total': 0, 'success': 0}
            language_stats[language]['total'] += 1
            if result['success']:
                language_stats[language]['success'] += 1
        return language_stats

    def _calculate_strategy_stats(self, repair_results: List[Dict]) -> Dict:
        """计算策略统计"""
        strategy_stats = {}
        for result in repair_results:
            strategy = result['strategy']
            if strategy not in strategy_stats:
                strategy_stats[strategy] = {'total': 0, 'success': 0}
            strategy_stats[strategy]['total'] += 1
            if result['success']:
                strategy_stats[strategy]['success'] += 1
        return strategy_stats

    def _generate_unified_text_report(self, detailed_results: List[Dict], repair_summary: Dict[str, Any],
                                      total_time: float, project_path: str, defect_report_path: str,
                                      language: str, min_severity: str) -> str:
        """生成统一的文本报告 - 修复版本"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = f"unified_repair_report_{timestamp}.txt"

        report_content = []
        report_content.append("=" * 80)
        report_content.append("统一代码修复系统详细报告")
        report_content.append("=" * 80)
        report_content.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_content.append(f"项目路径: {project_path}")
        report_content.append(f"缺陷报告: {defect_report_path}")
        report_content.append(f"目标语言: {language}")
        report_content.append(f"最小严重程度: {min_severity}")  # 新增
        report_content.append(f"配置参数: 线程数={self.max_workers}")
        report_content.append(f"总执行时间: {total_time:.2f}秒")
        report_content.append("")

        # 统计信息
        total_tasks = len(detailed_results)
        passed_tests = sum(1 for result in detailed_results if result.get('success', False))
        success_rate = (passed_tests / total_tasks) * 100 if total_tasks > 0 else 0

        report_content.append(f"总体统计:")
        report_content.append(f"  总修复任务: {total_tasks}")
        report_content.append(f"  成功修复: {passed_tests}")
        report_content.append(f"  修复失败: {total_tasks - passed_tests}")
        report_content.append(f"  修复成功率: {success_rate:.2f}%")
        report_content.append("")

        # 按语言统计
        language_stats = self._calculate_language_stats(detailed_results)
        report_content.append("按语言统计:")
        for lang, stats in language_stats.items():
            passed_count = stats['success']
            total_count = stats['total']
            rate = (passed_count / total_count) * 100 if total_count > 0 else 0
            report_content.append(f"  {lang}: {passed_count}/{total_count} ({rate:.2f}%)")
        report_content.append("")

        # 写入文件
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(report_content))

        return report_path

    def _save_unified_json_report(self, repair_summary: Dict[str, Any], detailed_results: List[Dict],
                                  total_time: float, project_path: str, defect_report_path: str, language: str,
                                  min_severity: str):
        """保存统一的JSON报告 - 修复版本"""
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "project_info": {
                "project_path": project_path,
                "target_language": language,
                "min_severity": min_severity,  # 新增
                "defect_report_path": defect_report_path
            },
            "configuration": {
                "max_workers": self.max_workers,
                "total_execution_time_seconds": total_time
            },
            "summary": {
                "total_tasks": repair_summary['total_tasks'],
                "successful_repairs": repair_summary['successful_repairs'],
                "failed_repairs": repair_summary['failed_repairs'],
                "success_rate": repair_summary['success_rate']
            },
            "language_statistics": self._calculate_language_stats(detailed_results if detailed_results else []),
            "detailed_results": detailed_results if detailed_results else []
        }

        report_path = f"unified_repair_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        logger.info(f"📄 统一JSON报告已保存: {report_path}")

    def run_unified_workflow(self, project_path: str, defect_report_path: str,
                             language: str = "auto", max_tasks: int = 30, min_severity: str = "MEDIUM"):
        """运行统一工作流程 - 修复版本"""
        logger.info("🚀 开始统一代码修复系统工作流程")
        logger.info(f"项目路径: {project_path}")
        logger.info(f"缺陷报告: {defect_report_path}")
        logger.info(f"目标语言: {language}")
        logger.info(f"最小严重程度: {min_severity}")  # 新增
        logger.info(f"最大任务数: {max_tasks}")

        # 在开始前清空修复结果
        self.code_fixer.clear_results()
        self.code_fixer.api_call_count = 0
        self.code_fixer.max_api_calls = 20

        start_time = time.time()

        try:
            # 1. 检测项目语言（如果需要）
            if language == "auto":
                language_stats = self.detect_project_language(project_path)
                detected_language = language_stats.get("primary_language", "unknown")
                if detected_language in ["python", "cpp"]:
                    language = detected_language
                    logger.info(f"自动检测到项目语言: {language}")
                else:
                    logger.warning(f"无法自动检测项目语言，使用默认处理")
                    language = "all"

            # 2. 加载缺陷报告（使用严重程度过滤）
            defect_report = self.load_defect_report(defect_report_path, language, min_severity)

            if not defect_report.files:
                logger.info("🎉 没有需要修复的缺陷，工作完成！")
                return

            # 3. 生成修复计划
            repair_plan = self.generate_repair_plan(defect_report, language)

            if repair_plan.total_tasks == 0:
                logger.info("🎉 没有需要修复的缺陷，工作完成！")
                return

            # 4. 限制任务数量
            if repair_plan.total_tasks > max_tasks:
                logger.warning(f"任务数量过多 ({repair_plan.total_tasks})，限制为前{max_tasks}个高优先级任务")
                repair_plan.tasks = repair_plan.tasks[:max_tasks]
                repair_plan.total_tasks = len(repair_plan.tasks)

            logger.info(f"将处理 {repair_plan.total_tasks} 个修复任务")

            # 5. 执行修复
            repair_summary = self.execute_repairs(repair_plan, defect_report)

            # 6. 生成报告
            total_time = time.time() - start_time
            self.generate_comprehensive_report(repair_summary, total_time, project_path, defect_report_path, language,
                                               min_severity)

            logger.info("🎉 统一代码修复工作流程完成！")

        except Exception as e:
            logger.error(f"工作流程执行失败: {str(e)}")
            raise


def main():
    """统一修复主函数 - 修复版本"""
    # 配置参数
    PROJECT_PATH = input("请输入项目路径: ").strip() or "."
    DEFECT_REPORT_PATH = input("请输入缺陷报告路径: ").strip() or "defect_report.json"
    LANGUAGE = input("请输入目标语言 (python/cpp/auto): ").strip().lower() or "auto"
    MIN_SEVERITY = input("请输入最小严重程度 (CRITICAL/HIGH/MEDIUM/LOW): ").strip().upper() or "MEDIUM"  # 新增
    MAX_TASKS = int(input("请输入最大任务数: ").strip() or "30")
    MAX_WORKERS = int(input("请输入并行线程数: ").strip() or "1")

    # 验证路径
    if not os.path.exists(PROJECT_PATH):
        logger.error(f"项目路径不存在: {PROJECT_PATH}")
        return

    if not os.path.exists(DEFECT_REPORT_PATH):
        logger.error(f"缺陷报告文件不存在: {DEFECT_REPORT_PATH}")
        logger.info("请确保缺陷检测Agent已运行并生成了缺陷报告")
        return

    # 验证语言参数
    if LANGUAGE not in ["python", "cpp", "auto", "all"]:
        logger.warning(f"不支持的语言: {LANGUAGE}，使用自动检测")
        LANGUAGE = "auto"

    # 验证严重程度参数
    if MIN_SEVERITY not in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
        logger.warning(f"不支持的严重程度: {MIN_SEVERITY}，使用MEDIUM")
        MIN_SEVERITY = "MEDIUM"

    logger.info("统一代码修复系统配置:")
    logger.info(f"  - 项目路径: {PROJECT_PATH}")
    logger.info(f"  - 缺陷报告: {DEFECT_REPORT_PATH}")
    logger.info(f"  - 目标语言: {LANGUAGE}")
    logger.info(f"  - 最小严重程度: {MIN_SEVERITY}")  # 新增
    logger.info(f"  - 最大任务数: {MAX_TASKS}")
    logger.info(f"  - 并行线程数: {MAX_WORKERS}")

    # 创建并运行统一修复系统
    repair_system = UnifiedRepairSystem(max_workers=MAX_WORKERS)
    repair_system.run_unified_workflow(PROJECT_PATH, DEFECT_REPORT_PATH, LANGUAGE, MAX_TASKS, MIN_SEVERITY)


if __name__ == "__main__":
    # 安装进度条库: pip install tqdm
    main()