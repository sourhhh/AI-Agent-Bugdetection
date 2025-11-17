import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from test_fix_evaluator import TestCase, FixEvaluator


def create_backend_config_test_cases() -> list[TestCase]:
    """创建后端配置修复测试用例 - 修正版本"""

    test_cases = [
        # 1. 数据库连接配置 - 使用正确的缺陷类型和消息
        TestCase(
            name="数据库连接配置修复",
            original_code='''DATABASE_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'user': 'admin',
    'password': 'password123'
}''',
            expected_fixed_code='''import os

DATABASE_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'user': os.getenv('DB_USER', 'admin'),
    'password': os.getenv('DB_PASSWORD', '')
}''',
            defect_type="security",  # 保持security类型，因为涉及密码
            defect_message="数据库配置包含硬编码的密码和连接信息",
            line_number=1
        ),

        # 2. API密钥配置 - 使用正确的缺陷类型
        TestCase(
            name="API密钥配置修复",
            original_code='''API_KEYS = {
    'openai': 'sk-1234567890abcdef',
    'stripe': 'sk_test_1234567890'
}''',
            expected_fixed_code='''import os

API_KEYS = {
    'openai': os.getenv('OPENAI_API_KEY', ''),
    'stripe': os.getenv('STRIPE_API_KEY', '')
}''',
            defect_type="security",
            defect_message="API密钥不应硬编码在代码中",
            line_number=1
        ),

        # 3. 调试模式配置 - 创建新的配置缺陷类型
        TestCase(
            name="调试模式配置修复",
            original_code='''DEBUG = True
ALLOWED_HOSTS = ['*']''',
            expected_fixed_code='''import os

DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')''',
            defect_type="config",  # 新增config类型
            defect_message="生产环境配置不应硬编码，应使用环境变量",
            line_number=1
        ),

        # 4. 缓存配置 - 使用配置缺陷类型
        TestCase(
            name="缓存配置修复",
            original_code='''CACHE_CONFIG = {
    'backend': 'redis',
    'location': 'redis://localhost:6379/0',
    'timeout': 300
}''',
            expected_fixed_code='''import os

CACHE_CONFIG = {
    'backend': 'redis',
    'location': os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
    'timeout': int(os.getenv('CACHE_TIMEOUT', 300))
}''',
            defect_type="config",
            defect_message="缓存配置应支持环境变量覆盖",
            line_number=1
        ),

        # 5. 日志配置 - 使用配置缺陷类型
        TestCase(
            name="日志配置修复",
            original_code='''LOG_CONFIG = {
    'level': 'INFO',
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
}''',
            expected_fixed_code='''import os
import logging

LOG_CONFIG = {
    'level': os.getenv('LOG_LEVEL', 'INFO'),
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
}''',
            defect_type="config",
            defect_message="日志配置应支持环境变量配置",
            line_number=1
        ),

        # 6. 跨域配置 - 使用配置缺陷类型
        TestCase(
            name="跨域配置修复",
            original_code='''CORS_CONFIG = {
    'allow_origins': ['*'],
    'allow_credentials': True
}''',
            expected_fixed_code='''import os

CORS_CONFIG = {
    'allow_origins': os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost:3000').split(','),
    'allow_credentials': True
}''',
            defect_type="config",
            defect_message="跨域配置不应使用通配符，应支持环境变量配置",
            line_number=1
        )
    ]

    return test_cases


def run_backend_config_tests():
    """运行后端配置修复测试"""
    print("开始后端配置修复测试...")
    print("=" * 50)

    evaluator = FixEvaluator()
    test_cases = create_backend_config_test_cases()

    results = evaluator.run_test_suite(test_cases)
    report = evaluator.generate_detailed_report(results)

    print(report)

    # 保存结果
    os.makedirs("test_results", exist_ok=True)
    with open("test_results/backend_config_results.txt", "w", encoding="utf-8") as f:
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
    with open("test_results/backend_config_results.json", "w", encoding="utf-8") as f:
        json.dump(json_result, f, indent=2, ensure_ascii=False)

    print(f"\n结果已保存到 test_results/ 目录")
    return results["success_rate"]


if __name__ == "__main__":
    run_backend_config_tests()
