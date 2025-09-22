# 新增：手动添加项目根目录到模块搜索路径（解决ModuleNotFoundError）
import os
import sys
# 获取项目根目录（tests文件夹的父目录）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 以下是原有代码，无需修改
import json
from agents.defect_detector import DefectDetector
from schemas.project_context import ProjectContext
from schemas.defect_report import DefectReport


def test_three_tools_work_together():
    """验证pylint、bandit、LLM三工具同时工作"""
    test_file = os.path.abspath("tests/test_code/sample_buggy.py")
    project_context = ProjectContext(
        project_root=os.path.dirname(test_file),
        python_files=[test_file],
        test_directories=[],
        dependencies=[],
        entry_points=[],
        requirements_path=None
    )

    detector = DefectDetector()
    report_json = detector.detect(project_context.to_json())
    report = DefectReport.from_json(report_json)
    print("=== 三工具检测报告 ===")
    print(report_json)

    all_defects = [d for file_def in report.files for d in file_def.defects]

    # 验证pylint（原始文件语法错误）
    has_pylint_syntax = any(
        d.tool == "pylint" and d.type == "syntax" and "syntax" in d.message.lower()
        for d in all_defects
    )
    assert has_pylint_syntax, "❌ pylint未检测到语法错误"

    # 验证bandit（临时文件安全漏洞）
    has_bandit_security = any(
        d.tool == "bandit" and d.type == "security" and "eval" in d.message.lower()
        for d in all_defects
    )
    assert has_bandit_security, "❌ bandit未检测到eval安全漏洞"

    # 验证LLM（原始文件逻辑错误）
    has_llm_logic = any(
        d.tool == "llm" and d.type == "logic" and ("zero" in d.message.lower() or "空列表" in d.message)
        for d in all_defects
    )
    assert has_llm_logic, "❌ LLM未检测到除零逻辑错误"

    assert len(all_defects) >= 3, f"缺陷数量不足，实际{len(all_defects)}个"

    print("✅ 三工具均正常工作！所有测试通过。")


if __name__ == "__main__":
    test_three_tools_work_together()