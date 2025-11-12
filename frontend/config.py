"""
前端配置管理 - 管理所有前端配置项
"""
import os
from typing import Dict, Any, Optional

# 尝试加载dotenv以支持.env文件
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("警告: dotenv模块未找到，将无法加载.env文件")


class Config:
    """前端配置类"""

    # 后端API配置
    BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:5000")
    API_TIMEOUT = int(os.getenv("API_TIMEOUT", "120"))  # 增加到120秒，适应AI处理时间

    # Gradio配置
    GRADIO_SERVER_PORT = int(os.getenv("GRADIO_SERVER_PORT", "7860"))
    GRADIO_SHARE = os.getenv("GRADIO_SHARE", "False").lower() == "true"
    GRADIO_HOST = os.getenv("GRADIO_HOST", "0.0.0.0")

    # 应用配置
    APP_NAME = "AI代码修复系统"
    APP_VERSION = "1.0.0"

    # 功能开关
    AUTO_ANALYZE = True
    ENABLE_BATCH_PROCESSING = True
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
    
    # API端点配置
    API_ENDPOINTS = {
        "HEALTH_CHECK": "/health",
        "FIX_CODE": "/fix-code",
        "ANALYZE_CODE": "/analyze-code",
        "GENERATE_PLAN": "/generate-plan",
        "UPLOAD_FILES": "/upload",
        "ANALYZE_PROJECT": "/analyze-project",
        "BATCH_FIX": "/batch-fix"
    }

    @classmethod
    def get_backend_url(cls):
        """获取后端URL"""
        return cls.BACKEND_URL.rstrip('/')
    
    @classmethod
    def get_api_endpoint(cls, endpoint_name: str) -> str:
        """获取API端点URL"""
        path = cls.API_ENDPOINTS.get(endpoint_name, "")
        return f"{cls.get_backend_url()}{path}"


# 创建一个全局配置实例
config = Config()