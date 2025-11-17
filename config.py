import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY', '')
    DEEPSEEK_API_URL = os.getenv('DEEPSEEK_API_URL', 'https://api.deepseek.com/chat/completions')
    MAX_RETRIES = int(os.getenv('MAX_RETRIES', 3))
    TIMEOUT = int(os.getenv('TIMEOUT', 30))

    # 修复策略配置
    REPAIR_STRATEGIES = {
        "replace_eval_with_ast_literal_eval": {
            "description": "用ast.literal_eval替换eval函数",
            "priority": "CRITICAL"
        },
        "fix_syntax_error": {
            "description": "修复语法错误",
            "priority": "HIGH"
        },
        "add_null_check": {
            "description": "添加空值检查",
            "priority": "MEDIUM"
        },
        "ai_automatic_fix": {
            "description": "AI自动修复",
            "priority": "LOW"
        }
    }