# 使用 pytest 对 main.py 进行测试

from main import add, subtract

def test_add():
    """测试加法函数"""
    assert add(2, 3) == 5
    assert add(-1, 1) == 0

def test_subtract():
    """测试减法函数"""
    assert subtract(5, 2) == 3
    assert subtract(0, 3) == -3