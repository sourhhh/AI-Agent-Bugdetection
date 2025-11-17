# 示例有缺陷的代码
SAMPLE_CODE_WITH_EVAL = """
def calculate_expression(expr):
    result = eval(expr)
    return result

def process_data(data):
    return data * 2
"""

# 修复后的代码
SAMPLE_FIXED_CODE = """
import ast

def calculate_expression(expr):
    result = ast.literal_eval(expr)
    return result

def process_data(data):
    return data * 2
"""