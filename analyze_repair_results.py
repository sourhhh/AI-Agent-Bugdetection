# analyze_repair_results.py
import json
from datetime import datetime


def analyze_failures():
    """分析修复失败原因"""
    with open('cpp_repair_report_20251026_161006.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    failures = [r for r in data['detailed_results'] if not r['success']]

    print("🔍 修复失败分析报告")
    print("=" * 50)

    failure_reasons = {}
    for failure in failures:
        changes = failure.get('changes_made', [])
        reason = "未知原因"

        if any("未通过验证" in str(change) for change in changes):
            reason = "验证失败"
        elif any("AI修复失败" in str(change) for change in changes):
            reason = "AI修复失败"
        elif any("连接错误" in str(change) for change in changes):
            reason = "网络连接问题"
        else:
            reason = "其他原因"

        failure_reasons[reason] = failure_reasons.get(reason, 0) + 1

    for reason, count in failure_reasons.items():
        print(f"{reason}: {count}次")

    # 建议
    print("\n💡 改进建议:")
    if "验证失败" in failure_reasons:
        print("- 放宽C++代码验证标准")
        print("- 优化错误关键词检测逻辑")
    if "AI修复失败" in failure_reasons:
        print("- 改进AI提示词工程")
        print("- 增加重试机制")
    if "网络连接问题" in failure_reasons:
        print("- 增加超时时间和重试次数")
        print("- 添加本地缓存机制")


if __name__ == "__main__":
    analyze_failures()