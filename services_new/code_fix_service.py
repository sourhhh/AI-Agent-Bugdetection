# code_fixer_backend/services/code_fix_service.py
import logging
import json
from typing import Dict, Any, List

from agents.code_fixer import CodeFixerAgent
from agents.decision_manager import DecisionManagerAgent
from schemas.defect_report import DefectReport, FileDefects, Defect
from schemas.fix_result import FixResult
from services_new.analysis_service import AnalysisService

logger = logging.getLogger(__name__)


class CodeFixService:
    """代码修复服务 - 完整包装Agent功能"""

    def __init__(self):
        self.code_fixer = CodeFixerAgent()
        self.decision_manager = DecisionManagerAgent()
        self.analysis_service = AnalysisService()

    def fix_single_code(self, code: str, language: str = "python") -> Dict[str, Any]:
        """修复单个代码片段 - 完整流程"""
        try:
            logger.info(f"开始修复代码: {len(code)}字符")

            # 1. 生成缺陷报告（AI优先，规则兜底）
            defect_report = self._create_defect_report_ai_first(code, "main.py")
            defect_report_json = defect_report.to_json()

            # 2. 生成修复计划
            repair_plan_json = self.decision_manager.analyze(defect_report_json)

            # 3. 执行修复
            fix_result_json = self.code_fixer.fix_code(repair_plan_json, defect_report_json)
            fix_result = FixResult.from_json(fix_result_json)

            # 4. 获取详细的修复结果
            detailed_results = self.code_fixer.get_fix_results()

            return {
                "success": True,
                "original_code": code,
                "fixed_code": fix_result.fixed_code,
                "changes": fix_result.changes_made,
                "confidence": fix_result.confidence,
                "defects_found": len(defect_report.files[0].defects),
                "repair_strategy": fix_result.strategy_used,
                "detailed_results": detailed_results
            }

        except Exception as e:
            logger.error(f"修复代码失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "original_code": code,
                "fixed_code": code,
                "changes": [],
                "confidence": 0.0
            }

    def fix_with_defect_report(self, defect_report_json: str) -> Dict[str, Any]:
        """基于已有的缺陷报告进行修复"""
        try:
            # 1. 生成修复计划
            repair_plan_json = self.decision_manager.analyze(defect_report_json)

            # 2. 执行修复
            fix_result_json = self.code_fixer.fix_code(repair_plan_json, defect_report_json)
            fix_result = FixResult.from_json(fix_result_json)

            # 3. 获取详细结果
            detailed_results = self.code_fixer.get_fix_results()

            return {
                "success": True,
                "fixed_code": fix_result.fixed_code,
                "changes": fix_result.changes_made,
                "confidence": fix_result.confidence,
                "strategy_used": fix_result.strategy_used,
                "detailed_results": detailed_results
            }

        except Exception as e:
            logger.error(f"基于缺陷报告修复失败: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def fix_multiple_files(self, files: Dict[str, str]) -> Dict[str, Any]:
        """修复多个文件"""
        try:
            # 1. 为所有文件生成缺陷报告（AI优先，规则兜底）
            file_defects_list = []
            all_defects = []

            for file_path, code in files.items():
                defects = self.analysis_service._detect_defects_ai_first(code)
                file_defects = FileDefects(
                    file_path=file_path,
                    defects=defects
                )
                file_defects_list.append(file_defects)
                all_defects.extend(defects)

            defect_report = DefectReport(
                files=file_defects_list,
                summary={"total_defects": len(all_defects)}
            )
            defect_report_json = defect_report.to_json()

            # 2. 生成修复计划
            repair_plan_json = self.decision_manager.analyze(defect_report_json)

            # 3. 执行修复
            fix_result_json = self.code_fixer.fix_code(repair_plan_json, defect_report_json)
            fix_result = FixResult.from_json(fix_result_json)

            # 4. 获取详细结果
            detailed_results = self.code_fixer.get_fix_results()

            return {
                "success": True,
                "files_fixed": len(files),
                "defects_found": len(all_defects),
                "changes": fix_result.changes_made,
                "confidence": fix_result.confidence,
                "detailed_results": detailed_results
            }

        except Exception as e:
            logger.error(f"修复多个文件失败: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def multi_round_fix(self, initial_code: str, feedback: str, max_retries: int = 3) -> Dict[str, Any]:
        """多轮修复机制"""
        try:
            # 初始修复
            initial_result = self.fix_single_code(initial_code)

            if not initial_result["success"]:
                return initial_result

            # 多轮修复
            fix_result_json = self.code_fixer.multi_round_fix(
                FixResult(
                    file_path="main.py",
                    original_code=initial_code,
                    fixed_code=initial_result["fixed_code"],
                    strategy_used=initial_result.get("repair_strategy", "ai_automatic_fix"),
                    changes_made=initial_result["changes"],
                    confidence=initial_result["confidence"]
                ).to_json(),
                feedback,
                max_retries
            )

            new_result = FixResult.from_json(fix_result_json)

            return {
                "success": True,
                "original_code": initial_code,
                "fixed_code": new_result.fixed_code,
                "changes": new_result.changes_made,
                "confidence": new_result.confidence,
                "rounds": 2,
                "improved": new_result.confidence > initial_result["confidence"]
            }

        except Exception as e:
            logger.error(f"多轮修复失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "original_code": initial_code,
                "fixed_code": initial_code
            }

    def _create_defect_report_ai_first(self, code: str, file_path: str) -> DefectReport:
        """创建缺陷报告（AI优先）"""
        defects = self.analysis_service._detect_defects_ai_first(code)

        file_defects = FileDefects(
            file_path=file_path,
            defects=defects
        )

        return DefectReport(
            files=[file_defects],
            summary={"total_defects": len(defects)}
        )

    def get_fix_statistics(self) -> Dict[str, Any]:
        """获取修复统计信息"""
        try:
            results = self.code_fixer.get_fix_results()

            if not results:
                return {
                    "total_fixes": 0,
                    "success_rate": 0,
                    "strategies_used": {}
                }

            total = len(results)
            successful = sum(1 for r in results if r.get('success', False))
            success_rate = (successful / total) * 100 if total > 0 else 0

            strategies = {}
            for result in results:
                strategy = result.get('strategy', 'unknown')
                if strategy not in strategies:
                    strategies[strategy] = 0
                strategies[strategy] += 1

            return {
                "total_fixes": total,
                "successful_fixes": successful,
                "success_rate": success_rate,
                "strategies_used": strategies
            }

        except Exception as e:
            logger.error(f"获取修复统计失败: {str(e)}")
            return {
                "total_fixes": 0,
                "success_rate": 0,
                "strategies_used": {},
                "error": str(e)
            }

    def clear_statistics(self):
        """清空修复统计"""
        self.code_fixer.clear_results()