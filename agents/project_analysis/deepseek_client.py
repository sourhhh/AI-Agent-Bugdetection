# -*- coding: utf-8 -*-
import os
import json
import requests
import math
from typing import List, Dict


class DeepSeekClient:
    def __init__(self, api_key: str = None, config_path: str = "config.json"):
        """
        初始化 DeepSeek 客户端
        :param api_key: DeepSeek API Key（可从环境变量读取）
        :param config_path: 配置文件路径
        """
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")

        # 加载配置文件
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        else:
            cfg = {}

        deepseek_cfg = cfg.get("deepseek", {})
        self.base_url = deepseek_cfg.get("sk-c340dc402a624d99a04dc0865da97eda", "https://platform.deepseek.com/usage")
        self.model = deepseek_cfg.get("model", "deepseek-coder")
        self.timeout = deepseek_cfg.get("timeout", 60)
        self.chunk_size = deepseek_cfg.get("chunk_size", 5)

    def _post_request(self, content: str) -> str:
        """发送一次请求给 DeepSeek"""
        if not self.api_key:
            return "未设置 DEEPSEEK_API_KEY，无法调用 DeepSeek API"

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "你是一个专业的软件项目分析助手。"},
                        {"role": "user", "content": content}
                    ],
                },
                timeout=self.timeout
            )
            data = response.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "无分析结果")
        except Exception as e:
            return f"调用 DeepSeek API 失败: {e}"

    def analyze_project(self, project_data: Dict) -> Dict:
        """
        分块上传项目结构给 DeepSeek
        :param project_data: {"project_structure": {...}, "test_directory": ...}
        :return: {"chunks": [...], "summary": "..."}
        """
        modules = project_data["project_structure"].get("modules", {})
        module_items = list(modules.items())

        if not module_items:
            return {"summary": "项目没有检测到 Python 源文件"}

        total_chunks = math.ceil(len(module_items) / self.chunk_size)
        chunk_results: List[str] = []

        for i in range(total_chunks):
            start = i * self.chunk_size
            end = start + self.chunk_size
            chunk = dict(module_items[start:end])

            content = f"以下是项目的一部分模块结构（第 {i+1}/{total_chunks} 块）：\n{json.dumps(chunk, indent=2, ensure_ascii=False)}\n请给出这些模块的作用和可能的设计意图。"
            analysis = self._post_request(content)
            chunk_results.append(analysis)

        # 总结性请求
        summary_prompt = f"这是该项目的分块分析结果：\n{chunk_results}\n\n请综合以上内容，总结整个项目的整体架构、依赖关系和潜在改进建议。"
        summary = self._post_request(summary_prompt)

        return {
            "chunks": chunk_results,
            "summary": summary
        }
