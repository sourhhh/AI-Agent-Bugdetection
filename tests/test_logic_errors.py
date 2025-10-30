import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from test_fix_evaluator import TestCase, FixEvaluator


def create_logic_error_test_cases() -> list[TestCase]:
    """创建逻辑错误测试用例 - 使用更明确的缺陷消息"""

    test_cases = [
        # 1. 函数参数空值检查 - 使用明确的变量名
        TestCase(
            name="函数参数空值检查",
            original_code='''def process_data(data):
    return data.upper()''',
            expected_fixed_code='''def process_data(data):
    if data is None:
        raise ValueError("data cannot be None")
    return data.upper()''',
            defect_type="logic",
            defect_message="参数 'data' 可能为None，缺少空值检查",
            line_number=2
        ),

        # 2. 除零检查 - 明确指定变量
        TestCase(
            name="除零检查",
            original_code='''def divide(a, b):
    return a / b''',
            expected_fixed_code='''def divide(a, b):
    if b == 0:
        raise ValueError("除数不能为零")
    return a / b''',
            defect_type="logic",
            defect_message="参数 'b' 可能为零，缺少除零检查",
            line_number=2
        ),

        # 3. 列表空检查 - 明确指定变量
        TestCase(
            name="列表空检查",
            original_code='''def get_first_item(items):
    return items[0]''',
            expected_fixed_code='''def get_first_item(items):
    if items is None or len(items) == 0:
        raise ValueError("items列表不能为空")
    return items[0]''',
            defect_type="logic",
            defect_message="参数 'items' 可能为空列表，缺少检查",
            line_number=2
        ),

        # 4. 更简单的测试用例
        TestCase(
            name="简单参数检查",
            original_code='''def hello(name):
    print(f"Hello {name}")''',
            expected_fixed_code='''def hello(name):
    if name is None:
        raise ValueError("name cannot be None")
    print(f"Hello {name}")''',
            defect_type="logic",
            defect_message="参数 'name' 缺少空值检查",
            line_number=2
        ),

        # 5. 变量使用检查
        TestCase(
            name="变量使用检查",
            original_code='''def calculate_total(price, quantity):
    total = price * quantity
    return total''',
            expected_fixed_code='''def calculate_total(price, quantity):
    if price is None or quantity is None:
        raise ValueError("price和quantity不能为None")
    total = price * quantity
    return total''',
            defect_type="logic",
            defect_message="变量 'price' 和 'quantity' 可能为None",
            line_number=2
        )
    ]

    return test_cases


def run_logic_error_tests():
    """运行逻辑错误修复测试"""
    print("开始逻辑错误修复测试...")
    print("=" * 50)

    evaluator = FixEvaluator()
    test_cases = create_logic_error_test_cases()

    results = evaluator.run_test_suite(test_cases)
    report = evaluator.generate_detailed_report(results)

    print(report)

    # 保存结果
    os.makedirs("test_results", exist_ok=True)
    with open("test_results/logic_error_results.txt", "w", encoding="utf-8") as f:
        f.write(report)

    # 保存JSON结果
    import json
    json_result = {
        "success_rate": results["success_rate"],
        "total_tests": results["total_tests"],
        "passed_tests": results["passed_tests"],
        "type_statistics": results["type_statistics"],
        "strategy_statistics": results["strategy_statistics"]
    }
    with open("test_results/logic_error_results.json", "w", encoding="utf-8") as f:
        json.dump(json_result, f, indent=2, ensure_ascii=False)

    print(f"\n结果已保存到 test_results/ 目录")
    return results["success_rate"]


if __name__ == "__main__":
    run_logic_error_tests()
