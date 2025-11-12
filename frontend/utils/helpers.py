"""
工具函数 - 提供通用的辅助功能
"""
import logging
import json
from typing import Any, Dict


def setup_logging(level=logging.INFO):
    """设置日志配置"""
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('frontend.log', encoding='utf-8')
        ]
    )
    return logging.getLogger(__name__)


def format_error_message(error: Any) -> str:
    """格式化错误信息"""
    if isinstance(error, dict):
        return error.get('error', str(error))
    elif hasattr(error, 'message'):
        return error.message
    else:
        return str(error)


def validate_code_snippet(code: str) -> tuple[bool, str]:
    """验证代码片段"""
    if not code or not code.strip():
        return False, "代码不能为空"

    if len(code) > 100000:  # 100KB限制
        return False, "代码长度超过限制"

    return True, ""