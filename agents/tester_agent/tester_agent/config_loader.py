import json
import os
import yaml

class ConfigLoader:
    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path

    def load_config(self) -> dict:
        """加载配置文件（支持 JSON / YAML）"""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"配置文件未找到: {self.config_path}")

        if self.config_path.endswith(".json"):
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)

        elif self.config_path.endswith((".yml", ".yaml")):
            with open(self.config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)

        else:
            raise ValueError("不支持的配置文件格式，仅支持 JSON 或 YAML")
