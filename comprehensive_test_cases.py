"""
Code Fixer Agent 综合测试用例
涵盖项目级代码修复的各种场景
"""

import tempfile
import os
from typing import Dict, List
from schemas.defect_report import Defect, FileDefects, DefectReport
from schemas.repair_plan import RepairTask, RepairPlan


class ComprehensiveTestCases:
    """综合测试用例生成器"""

    @staticmethod
    def create_security_test_case() -> Dict:
        """安全漏洞测试用例"""
        test_code = """
import pickle
import subprocess
import os

class DataProcessor:
    def process_untrusted_data(self, data):
        # 反序列化漏洞
        return pickle.loads(data)

    def execute_command(self, user_input):
        # 命令注入漏洞
        os.system(f"echo {user_input}")
        return subprocess.check_output(user_input, shell=True)

    def handle_password(self):
        # 硬编码密码
        password = "secret123"
        api_key = "sk_test_1234567890"
        return password + api_key

def calculate_expression(expr):
    # eval漏洞
    return eval(expr)

def sql_query(user_id):
    # SQL注入漏洞
    query = f"SELECT * FROM users WHERE id = {user_id}"
    return query
"""

        defects = [
            Defect(type="security", message="Use of insecure pickle.loads", line_number=8, severity="CRITICAL",
                   tool="bandit", confidence=0.95),
            Defect(type="security", message="Possible shell injection", line_number=12, severity="CRITICAL",
                   tool="bandit", confidence=0.9),
            Defect(type="security", message="Possible shell injection", line_number=13, severity="CRITICAL",
                   tool="bandit", confidence=0.9),
            Defect(type="security", message="Hardcoded password", line_number=17, severity="HIGH", tool="bandit",
                   confidence=0.8),
            Defect(type="security", message="Hardcoded API key", line_number=18, severity="HIGH", tool="bandit",
                   confidence=0.8),
            Defect(type="security", message="Use of insecure eval", line_number=22, severity="CRITICAL", tool="bandit",
                   confidence=0.95),
            Defect(type="security", message="Possible SQL injection", line_number=26, severity="HIGH", tool="bandit",
                   confidence=0.85)
        ]

        return {
            "code": test_code,
            "defects": defects,
            "expected_strategies": ["ai_automatic_fix"] * 7,
            "description": "多种安全漏洞综合测试"
        }

    @staticmethod
    def create_syntax_logic_test_case() -> Dict:
        """语法和逻辑错误测试用例"""
        test_code = """
def process_data(data):
    # 语法错误和逻辑问题
    if data = None:  # 应该用==
        return

    result = []
    for i in range(len(data))
        # 缺少冒号
        if data[i] > 10
            result.append(data[i] * 2)  # 缩进错误

    # 未使用的变量
    temp = "unused"

    # 可能的除零错误
    def calculate_ratio(a, b):
        return a / b  # 没有检查b是否为0

    # 类型错误
    def add_numbers(x, y):
        return x + y  # 可能连接字符串而不是相加

    return result

# 错误的函数调用
value = process_data(None)
print(value.lower())  # 可能None没有lower方法
"""

        defects = [
            Defect(type="syntax", message="Syntax error: invalid syntax", line_number=4, severity="HIGH", tool="pylint",
                   confidence=0.9),
            Defect(type="syntax", message="Expected ':'", line_number=8, severity="HIGH", tool="pylint",
                   confidence=0.9),
            Defect(type="syntax", message="Unexpected indent", line_number=9, severity="MEDIUM", tool="pylint",
                   confidence=0.8),
            Defect(type="logic", message="Variable 'temp' is unused", line_number=13, severity="LOW", tool="pylint",
                   confidence=0.7),
            Defect(type="logic", message="Possible division by zero", line_number=17, severity="MEDIUM", tool="pylint",
                   confidence=0.75),
            Defect(type="logic", message="Possible type error in addition", line_number=21, severity="MEDIUM",
                   tool="pylint", confidence=0.7),
            Defect(type="logic", message="Possible AttributeError", line_number=25, severity="MEDIUM", tool="pylint",
                   confidence=0.8)
        ]

        return {
            "code": test_code,
            "defects": defects,
            "expected_strategies": ["fix_syntax_error", "fix_syntax_error", "fix_indentation",
                                    "ai_automatic_fix", "add_null_check", "ai_automatic_fix", "add_null_check"],
            "description": "语法和逻辑错误综合测试"
        }

    @staticmethod
    def create_performance_test_case() -> Dict:
        """性能问题测试用例"""
        test_code = """
import time

def inefficient_processing(data):
    # 低效的算法
    result = []
    for item in data:
        if item in result:  # O(n^2) 复杂度
            continue
        result.append(item)

    # 不必要的重复计算
    for i in range(len(result)):
        for j in range(len(result)):
            if result[i] == result[j]:
                pass

    # 不必要的全局变量访问
    global config
    for item in result:
        process_item(item, config)

    return result

def process_item(item, config):
    # 模拟耗时操作
    time.sleep(0.001)
    return item * config.get('factor', 1)

# 大量的字符串拼接
def generate_report(data):
    report = ""
    for item in data:
        report += str(item) + "\\n"  # 低效的字符串拼接
    return report
"""

        defects = [
            Defect(type="performance", message="Inefficient membership check", line_number=6, severity="MEDIUM",
                   tool="pylint", confidence=0.8),
            Defect(type="performance", message="Inefficient nested loops", line_number=11, severity="MEDIUM",
                   tool="pylint", confidence=0.85),
            Defect(type="performance", message="Unnecessary global variable access", line_number=15, severity="LOW",
                   tool="pylint", confidence=0.7),
            Defect(type="performance", message="Inefficient string concatenation", line_number=26, severity="MEDIUM",
                   tool="pylint", confidence=0.8)
        ]

        return {
            "code": test_code,
            "defects": defects,
            "expected_strategies": ["ai_automatic_fix"] * 4,
            "description": "性能问题修复测试"
        }

    @staticmethod
    def create_code_quality_test_case() -> Dict:
        """代码质量测试用例"""
        test_code = """
class DataHandler:
    def __init__(self):
        self.data = None

    # 过长的函数
    def process_data(self, input_data, config_params, user_options, additional_settings=None):
        if additional_settings is None:
            additional_settings = {}

        # 复杂的嵌套条件
        if input_data is not None and len(input_data) > 0:
            for item in input_data:
                if item.get('status') == 'active':
                    if item['value'] > 100:
                        if config_params.get('enable_feature'):
                            if user_options.get('advanced_mode'):
                                # 魔法数字
                                result = item['value'] * 2.5
                            else:
                                result = item['value'] * 1.5
                        else:
                            result = item['value']

        # 重复代码
        if additional_settings.get('log_enabled'):
            print("Processing completed")
            print("Result: " + str(result))

        return result

    # 另一个重复的日志代码
    def another_method(self):
        print("Processing completed")
        print("Result: " + str("unknown"))
"""

        defects = [
            Defect(type="code_smell", message="Function too long", line_number=6, severity="MEDIUM", tool="pylint",
                   confidence=0.8),
            Defect(type="code_smell", message="Too many nested blocks", line_number=11, severity="MEDIUM",
                   tool="pylint", confidence=0.75),
            Defect(type="code_smell", message="Magic number used", line_number=15, severity="LOW", tool="pylint",
                   confidence=0.7),
            Defect(type="code_smell", message="Duplicate code", line_number=26, severity="LOW", tool="pylint",
                   confidence=0.8),
            Defect(type="code_smell", message="Duplicate code", line_number=32, severity="LOW", tool="pylint",
                   confidence=0.8)
        ]

        return {
            "code": test_code,
            "defects": defects,
            "expected_strategies": ["ai_automatic_fix"] * 5,
            "description": "代码质量问题修复测试"
        }

    @staticmethod
    def create_multi_file_test_case() -> List[Dict]:
        """多文件项目测试用例"""
        return [
            {
                "file_path": "utils/security.py",
                "code": """
import ast

def safe_eval(expr):
    return eval(expr)  # 不安全

def process_input(user_input):
    return user_input.strip()
""",
                "defects": [
                    Defect(type="security", message="Use of insecure eval", line_number=5, severity="CRITICAL",
                           tool="bandit", confidence=0.95)
                ]
            },
            {
                "file_path": "models/data_processor.py",
                "code": """
class DataProcessor:
    def __init__(self):
        self.data = None

    def process(self, input_data):
        if input_data = None:  # 语法错误
            return []

        result = []
        for item in input_data:
            result.append(item * 2)

        return result
""",
                "defects": [
                    Defect(type="syntax", message="Syntax error", line_number=6, severity="HIGH", tool="pylint",
                           confidence=0.9)
                ]
            },
            {
                "file_path": "main.py",
                "code": """
from utils.security import safe_eval
from models.data_processor import DataProcessor

def main():
    processor = DataProcessor()
    result = processor.process([1, 2, 3])
    print(safe_eval("1 + 1"))

    # 未处理异常
    risky_value = 10 / 0

if __name__ == "__main__":
    main()
""",
                "defects": [
                    Defect(type="logic", message="Division by zero", line_number=9, severity="HIGH", tool="pylint",
                           confidence=0.85)
                ]
            }
        ]

    @staticmethod
    def create_simple_security_test_case() -> Dict:
        """简单的安全漏洞测试用例（只有一个eval问题）"""
        test_code = """
    def calculate_expression(expr):
        result = eval(expr)
        return result
    """

        defects = [
            Defect(type="security", message="Use of insecure eval", line_number=3,
                   severity="CRITICAL", tool="bandit", confidence=0.95),
        ]

        return {
            "code": test_code,
            "defects": defects,
            "expected_strategies": ["replace_eval_with_ast_literal_eval"],
            "description": "简单的eval安全漏洞测试"
        }

    @staticmethod
    def create_simple_syntax_test_case() -> Dict:
        """简单的语法错误测试用例（只有一个赋值错误）"""
        test_code = """
    def process_data(data):
        if data = None:
            return
        return data
    """

        defects = [
            Defect(type="syntax", message="Syntax error: invalid syntax", line_number=3,
                   severity="HIGH", tool="pylint", confidence=0.9),
        ]

        return {
            "code": test_code,
            "defects": defects,
            "expected_strategies": ["fix_syntax_error"],
            "description": "简单的语法错误测试"
        }

    # 在 comprehensive_test_cases.py 中添加专门的简单测试用例
    @staticmethod
    def create_simple_eval_test_case() -> Dict:
        """简单的eval测试用例（只有eval问题）"""
        test_code = """def calculate_expression(expr):
        result = eval(expr)
        return result
    """

        defects = [
            Defect(type="security", message="Use of insecure eval", line_number=2,
                   severity="CRITICAL", tool="bandit", confidence=0.95),
        ]

        return {
            "code": test_code,
            "defects": defects,
            "expected_strategies": ["replace_eval_with_ast_literal_eval"],
            "description": "简单的eval安全漏洞测试"
        }

    @staticmethod
    def create_simple_syntax_test_case() -> Dict:
        """简单的语法错误测试用例（只有赋值错误）"""
        test_code = """def process_data(data):
        if data = None:
            return
        return data
    """

        defects = [
            Defect(type="syntax", message="Syntax error: invalid syntax", line_number=2,
                   severity="HIGH", tool="pylint", confidence=0.9),
        ]

        return {
            "code": test_code,
            "defects": defects,
            "expected_strategies": ["fix_syntax_error"],
            "description": "简单的语法错误测试"
        }

    # 在 comprehensive_test_cases.py 中添加
    @staticmethod
    def create_minimal_eval_test_case() -> Dict:
        """最小化的eval测试用例"""
        test_code = """def calculate_expression(expr):
        return eval(expr)
    """

        defects = [
            Defect(type="security", message="Use of insecure eval", line_number=2,
                   severity="CRITICAL", tool="bandit", confidence=0.95),
        ]

        return {
            "code": test_code,
            "defects": defects,
            "expected_strategies": ["replace_eval_with_ast_literal_eval"],
            "description": "最小化的eval安全漏洞测试"
        }
    # 在 comprehensive_test_cases.py 中添加
    @staticmethod
    def create_very_simple_eval_test_case() -> Dict:
        """非常简单的eval测试用例（没有缩进问题）"""
        test_code = """def calculate_expression(expr):
        return eval(expr)
    """

        defects = [
            Defect(type="security", message="Use of insecure eval", line_number=2,
                   severity="CRITICAL", tool="bandit", confidence=0.95),
        ]

        return {
            "code": test_code,
            "defects": defects,
            "expected_strategies": ["replace_eval_with_ast_literal_eval"],
            "description": "非常简单的eval安全漏洞测试"
        }