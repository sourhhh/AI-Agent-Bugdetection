import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.code_fixer import CodeFixerAgent
from schemas.defect_report import Defect, FileDefects, DefectReport
from schemas.repair_plan import RepairTask, RepairPlan


def debug_add_null_check():
    """调试 add_null_check 策略"""
    print("调试 add_null_check 策略...")

    fixer = CodeFixerAgent()

    # 测试代码
    test_code = '''def process_data(data):
    return data.upper()'''

    # 创建缺陷
    defect = Defect(
        type="logic",
        message="参数'data'缺少空值检查",
        line_number=2,
        severity="HIGH",
        tool="pylint",
        confidence=0.9
    )

    # 执行修复策略
    print("原始代码:")
    print(test_code)
    print("\n执行 add_null_check 策略...")

    fixed_code, changes = fixer._add_null_check_strategy(
        test_code,
        defect,
        {"defect_type": "logic", "message": "参数'data'缺少空值检查"}
    )

    print(f"修复变更: {changes}")
    print("修复后代码:")
    print(fixed_code)

    # 测试变量提取功能
    print("\n测试变量提取:")
    test_messages = [
        "参数'data'缺少空值检查",
        "变量'items'可能为None",
        "缺少对输入值的检查"
    ]

    for msg in test_messages:
        variable = fixer._extract_variable_from_message(msg, "return data.upper()")
        print(f"消息: '{msg}' -> 提取变量: '{variable}'")


if __name__ == "__main__":
    debug_add_null_check()
