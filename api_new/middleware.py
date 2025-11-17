import os


def is_ai_available() -> bool:
    """检查是否配置了DeepSeek API密钥"""
    return bool(os.getenv('DEEPSEEK_API_KEY'))


def require_ai_available() -> dict:
    """返回标准的AI不可用响应负载（供路由使用，可选）"""
    return {
        "success": False,
        "error": "AI服务不可用：未配置DEEPSEEK_API_KEY",
        "ai_available": False
    }
