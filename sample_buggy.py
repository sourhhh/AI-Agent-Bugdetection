# tests/test_code/sample_buggy.py
"""
混合缺陷测试代码（确保pylint识别语法错误）
1. 语法错误：函数参数缺少逗号（pylint必报error，非致命）
2. 安全漏洞：eval函数（bandit目标）
3. 逻辑错误：空列表除零（LLM目标）
"""

# -------------------------- 1. 真正的语法错误（pylint必检测） --------------------------
# 错误点：参数a和b之间缺少逗号（Python语法错误，pylint会标记为error）
def syntax_error_func(a b):  # ❌ 函数参数缺少逗号（语法错误，pylint必报）
    return a + b


# -------------------------- 2. 安全漏洞（bandit已正常检测） --------------------------
def security_vuln_func():
    user_input = input("请输入命令：")
    return eval(user_input)  # ✅ bandit已检测到


# -------------------------- 3. 逻辑错误（LLM已正常检测） --------------------------
def logic_error_func(numbers):
    return sum(numbers) / len(numbers)  # ✅ LLM已检测到