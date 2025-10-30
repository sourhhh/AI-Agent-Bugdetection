import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agents.code_fixer import CodeFixerAgent
from schemas.defect_report import Defect, FileDefects, DefectReport
from schemas.repair_plan import RepairTask


def test_cpp_include_fix():
    """测试C++头文件修复 - 多种情况"""
    fixer = CodeFixerAgent()

    test_cases = [
        {
            "name": "缺失vector头文件",
            "code": """
#include <iostream>
using namespace std;

int main() {
    vector<int> nums;  // 这里需要<vector>
    return 0;
}
""",
            "defect_message": "Include file: <vector>",
            "expected_header": "vector"
        },
        {
            "name": "缺失string头文件",
            "code": """
#include <iostream>
using namespace std;

int main() {
    string name = "test";
    return 0;
}
""",
            "defect_message": "Unable to find include file: 'string'",
            "expected_header": "string"
        }
    ]

    for test_case in test_cases:
        print(f"\n=== 测试: {test_case['name']} ===")

        defect = Defect(
            type="syntax",
            message=test_case["defect_message"],
            line_number=5,  # vector<int> 所在行
            severity="HIGH",
            tool="pylint",
            confidence=0.8
        )

        fixed_code, changes = fixer._fix_cpp_include_issues_strategy(
            test_case["code"], defect, {}, "cpp"
        )

        print(f"修复变更: {changes}")
        print(f"是否添加了头文件: {any(test_case['expected_header'] in change for change in changes)}")
        print(f"修复后代码:\n{fixed_code}")


def test_cpp_memory_leak_fix():
    """测试C++内存泄漏修复"""
    fixer = CodeFixerAgent()

    test_code = """
#include <iostream>
using namespace std;

class MyClass {
public:
    void createObject() {
        MyClass* obj = new MyClass();  // 可能内存泄漏
        obj->doSomething();
    }

    void doSomething() {
        cout << "Doing something" << endl;
    }
};
"""

    defect = Defect(
        type="memory",
        message="Potential memory leak: object created with 'new' but no 'delete'",
        line_number=7,  # new MyClass() 所在行
        severity="HIGH",
        tool="pylint",
        confidence=0.8
    )

    print("\n=== 测试: 内存泄漏修复 ===")
    fixed_code, changes = fixer._fix_cpp_memory_leak_strategy(test_code, defect, {}, "cpp")

    print(f"修复变更: {changes}")
    print(f"修复后代码:\n{fixed_code}")


def test_qt_memory_management():
    """测试Qt对象内存管理"""
    fixer = CodeFixerAgent()

    qt_code = """
#include <QWidget>
#include <QLabel>

class MyWidget : public QWidget {
public:
    MyWidget(QWidget* parent = nullptr) : QWidget(parent) {
        QLabel* label = new QLabel("Hello");  // Qt对象需要设置父对象
        // 这里应该调用 label->setParent(this);
    }
};
"""

    defect = Defect(
        type="memory",
        message="Qt object created with 'new' but no parent set",
        line_number=7,
        severity="HIGH",
        tool="pylint",
        confidence=0.8
    )

    print("\n=== 测试: Qt对象内存管理 ===")
    fixed_code, changes = fixer._fix_cpp_memory_leak_strategy(qt_code, defect, {}, "cpp")

    print(f"修复变更: {changes}")
    print(f"修复后代码:\n{fixed_code}")


if __name__ == "__main__":
    print("测试增强的C++修复功能...")
    test_cpp_include_fix()
    test_cpp_memory_leak_fix()
    test_qt_memory_management()