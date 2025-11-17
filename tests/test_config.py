import os


# 测试配置
class TestConfig:
    # 测试文件目录
    TEST_DATA_DIR = "test_data"

    # 结果输出目录
    RESULTS_DIR = "test_results"

    # 临时文件目录
    TEMP_DIR = "temp_test_files"

    # 测试超时时间（秒）
    TEST_TIMEOUT = 30

    # 是否启用详细日志
    VERBOSE_LOGGING = True

    # AI相关配置
    AI_MAX_RETRIES = 3
    AI_TIMEOUT = 30

    @classmethod
    def setup_directories(cls):
        """创建必要的目录"""
        os.makedirs(cls.TEST_DATA_DIR, exist_ok=True)
        os.makedirs(cls.RESULTS_DIR, exist_ok=True)
        os.makedirs(cls.TEMP_DIR, exist_ok=True)
