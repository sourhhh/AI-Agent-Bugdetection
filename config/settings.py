"""
后端配置管理 - 集中管理所有配置项
"""
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    # dotenv is optional in test environments; continue without loading .env
    pass


class Config:
    """应用配置类"""

    # Flask基础配置
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key')

    # CORS配置 - 允许的前端域名
    CORS_ORIGINS = [
        "http://localhost:7860",  # Gradio默认端口
        "http://127.0.0.1:7860",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # API配置
    API_TITLE = "AI Code Fixer API"
    API_VERSION = "1.0.0"

    # 服务配置
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB文件大小限制

    # AI服务配置
    DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
    AI_SERVICE_TIMEOUT = 30

    @classmethod
    def get_allowed_origins(cls):
        """获取允许的跨域源"""
        additional_origins = os.environ.get('ALLOWED_ORIGINS', '').split(',')
        return cls.CORS_ORIGINS + [origin.strip() for origin in additional_origins if origin.strip()]