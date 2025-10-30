import json
from datetime import datetime
from tests.test_logic_errors import run_logic_error_tests
from tests.test_security_fixes import run_security_tests
from tests.test_backend_config import run_backend_config_tests


def run_comprehensive_evaluation():
    """运行全面的修复成功率评估"""
    print("开始全面的代码修复Agent评估...")
    print("=" * 60)

    results = {}

    # 运行逻辑错误测试
    print("\n1. 逻辑错误修复测试")
    logic_success_rate = run_logic_error_tests()
    results['logic_errors'] = logic_success_rate

    # 运行安全性测试
    print("\n2. 安全性修复测试")
    security_success_rate = run_security_tests()
    results['security_fixes'] = security_success_rate

    # 运行后端配置测试
    print("\n3. 后端配置修复测试")
    config_success_rate = run_backend_config_tests()
    results['backend_config'] = config_success_rate

    # 计算总体成功率
    overall_success_rate = (logic_success_rate + security_success_rate + config_success_rate) / 3

    # 生成最终报告
    final_report = generate_final_report(results, overall_success_rate)
    print(final_report)

    # 保存最终结果
    save_final_results(results, overall_success_rate)

    return overall_success_rate


def generate_final_report(results: dict, overall_rate: float) -> str:
    """生成最终评估报告"""
    report = []
    report.append("=" * 60)
    report.append("代码修复Agent综合评估报告")
    report.append("=" * 60)
    report.append(f"评估时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("")

    report.append("分类测试结果:")
    report.append(f"  逻辑错误修复: {results['logic_errors']:.2%}")
    report.append(f"  安全性修复: {results['security_fixes']:.2%}")
    report.append(f"  后端配置修复: {results['backend_config']:.2%}")
    report.append("")
    report.append(f"总体修复成功率: {overall_rate:.2%}")
    report.append("")

    # 性能评级
    if overall_rate >= 0.9:
        rating = "优秀"
        suggestion = "修复Agent表现卓越，可以投入生产环境使用"
    elif overall_rate >= 0.7:
        rating = "良好"
        suggestion = "修复Agent表现良好，建议继续优化特定策略"
    elif overall_rate >= 0.5:
        rating = "一般"
        suggestion = "修复Agent需要进一步改进，建议重点优化低成功率策略"
    else:
        rating = "需要改进"
        suggestion = "修复Agent需要重大改进，建议重新设计核心策略"

    report.append(f"性能评级: {rating}")
    report.append(f"改进建议: {suggestion}")
    report.append("")

    report.append("建议优化方向:")
    if results['logic_errors'] < 0.7:
        report.append("  • 加强逻辑错误检测和修复能力")
    if results['security_fixes'] < 0.7:
        report.append("  • 提升安全性漏洞修复的准确性")
    if results['backend_config'] < 0.7:
        report.append("  • 改进配置相关问题的修复策略")

    return '\n'.join(report)


def save_final_results(results: dict, overall_rate: float):
    """保存最终评估结果"""
    final_result = {
        "evaluation_time": datetime.now().isoformat(),
        "overall_success_rate": overall_rate,
        "category_rates": results,
        "performance_rating": get_performance_rating(overall_rate)
    }

    with open("comprehensive_evaluation_results.json", "w", encoding="utf-8") as f:
        json.dump(final_result, f, indent=2, ensure_ascii=False)


def get_performance_rating(rate: float) -> str:
    """获取性能评级"""
    if rate >= 0.9:
        return "优秀"
    elif rate >= 0.7:
        return "良好"
    elif rate >= 0.5:
        return "一般"
    else:
        return "需要改进"


if __name__ == "__main__":
    success_rate = run_comprehensive_evaluation()
    print(f"\n评估完成！总体成功率: {success_rate:.2%}")
