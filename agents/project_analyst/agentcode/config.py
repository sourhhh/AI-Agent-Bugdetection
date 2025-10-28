# -*- coding: utf-8 -*-
import json
import os
from typing import Dict, Any


def load_config(config_path: str = "config.json") -> Dict[str, Any]:
    """加载配置文件，返回配置字典"""
    default_config = {
        "deepseek": {
            "api_base": "https://platform.deepseek.com/usage",
            "model": "deepseek-coder",
            "timeout": 60,
            "chunk_size": 5
        }
    }

    if not os.path.exists(config_path):
        return default_config

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            user_config = json.load(f)
        # 合并默认配置和用户配置（用户配置覆盖默认）
        default_config["deepseek"].update(user_config.get("deepseek", {}))
        return default_config
    except json.JSONDecodeError:
        raise ValueError(f"配置文件{config_path}格式错误")