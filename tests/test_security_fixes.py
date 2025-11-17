import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from test_fix_evaluator import TestCase, FixEvaluator


def create_security_test_cases() -> list[TestCase]:
    """创建安全性修复测试用例 - 修正行号版本"""

    test_cases = [
        # 1. eval函数使用
        TestCase(
            name="eval函数替换",
            original_code='''def calculate_expression(expr):
    return eval(expr)''',
            expected_fixed_code='''import ast

def calculate_expression(expr):
    return ast.literal_eval(expr)''',
            defect_type="security",
            defect_message="使用eval函数可能导致代码注入漏洞",
            line_number=2  # return eval(expr) 在第2行
        ),

        # 2. 多个eval调用
        TestCase(
            name="多个eval调用替换",
            original_code='''def process_data(data):
    config = eval(data.get('config', '{}'))
    value = eval(data.get('value', '0'))
    return config, value''',
            expected_fixed_code='''import ast

def process_data(data):
    config = ast.literal_eval(data.get('config', '{}'))
    value = ast.literal_eval(data.get('value', '0'))
    return config, value''',
            defect_type="security",
            defect_message="多处使用eval函数存在安全风险",
            line_number=2  # 第一个eval在第2行
        ),

        # 3. pickle反序列化 - 修正行号
        TestCase(
            name="pickle反序列化风险",
            original_code='''import pickle

def load_data(file_path):
    with open(file_path, 'rb') as f:
        return pickle.load(f)''',
            expected_fixed_code='''import pickle

# 警告: pickle反序列化可能存在安全风险，建议使用更安全的序列化格式如JSON
def load_data(file_path):
    with open(file_path, 'rb') as f:
        return pickle.load(f)''',
            defect_type="security",
            defect_message="pickle反序列化可能执行任意代码",
            line_number=5  # return pickle.load(f) 在第5行
        ),

        # 4. 硬编码密码 - 修正行号
        TestCase(
            name="硬编码密码",
            original_code='''DB_PASSWORD = "mysecretpassword123"

def connect_database():
    return connect(host="localhost", password=DB_PASSWORD)''',
            expected_fixed_code='''import os

DB_PASSWORD = os.getenv("DB_PASSWORD", "")

def connect_database():
    return connect(host="localhost", password=DB_PASSWORD)''',
            defect_type="security",
            defect_message="代码中包含硬编码的密码",
            line_number=1  # DB_PASSWORD = ... 在第1行
        ),

        # 5. SQL注入风险 - 修正行号
        TestCase(
            name="SQL注入防护",
            original_code='''def get_user(user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    return execute_query(query)''',
            expected_fixed_code='''def get_user(user_id):
    query = "SELECT * FROM users WHERE id = %s"
    return execute_query(query, (user_id,))''',
            defect_type="security",
            defect_message="SQL查询使用字符串格式化，存在注入风险",
            line_number=2  # query = f"SELECT ... 在第2行
        ),

        # 6. 命令注入风险 - 修正行号
        TestCase(
            name="命令注入防护",
            original_code='''import os

def list_files(directory):
    return os.popen(f"ls {directory}").read()''',
            expected_fixed_code='''import os
import subprocess

def list_files(directory):
    result = subprocess.run(['ls', directory], capture_output=True, text=True)
    return result.stdout''',
            defect_type="security",
            defect_message="使用os.popen存在命令注入风险",
            line_number=4  # return os.popen(...) 在第4行
        )
    ]

    return test_cases


def run_security_tests():
    """运行安全性修复测试"""
    print("开始安全性修复测试...")
    print("=" * 50)

    evaluator = FixEvaluator()
    test_cases = create_security_test_cases()

    results = evaluator.run_test_suite(test_cases)
    report = evaluator.generate_detailed_report(results)

    print(report)

    # 保存结果
    os.makedirs("test_results", exist_ok=True)
    with open("test_results/security_test_results.txt", "w", encoding="utf-8") as f:
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
    with open("test_results/security_test_results.json", "w", encoding="utf-8") as f:
        json.dump(json_result, f, indent=2, ensure_ascii=False)

    print(f"\n结果已保存到 test_results/ 目录")
    return results["success_rate"]


if __name__ == "__main__":
    run_security_tests()
