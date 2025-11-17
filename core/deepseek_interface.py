# core/deepseek_interface.py
import os
import requests
from typing import Optional


class DeepSeekInterface:
    """
    DeepSeek API交互类（支撑B角色LLM检测功能）
    封装API调用逻辑，供DefectDetector调用LLM能力
    """

    def __init__(self):
        """初始化：读取API密钥、配置请求头"""
        # 从环境变量获取密钥（避免硬编码，符合安全规范）
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("❌ 请设置环境变量 DEEPSEEK_API_KEY（从DeepSeek控制台获取）")

        # API基础配置（参考DeepSeek官方文档）
        self.base_url = "https://api.deepseek.com/v1/chat/completions"
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

    def query(self, prompt: str, model: str = "deepseek-coder", temperature: float = 0.1) -> Optional[str]:
        """
        调用DeepSeek LLM获取响应
        :param prompt: 提示词（引导LLM检测缺陷）
        :param model: 模型名称（deepseek-coder适合代码任务）
        :param temperature: 随机性（0.1确保结果稳定，符合代码检测需求）
        :return: LLM响应文本；调用失败返回None
        """
        # 构造API请求体（符合DeepSeek ChatCompletion格式）
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature
        }

        try:
            # 发送POST请求
            response = requests.post(
                self.base_url,
                headers=self.headers,
                json=payload,
                timeout=15  # 15秒超时
            )
            response.raise_for_status()  # 抛出HTTP错误（如401密钥无效）

            # 解析响应结果
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()

        except requests.exceptions.RequestException as e:
            print(f"❌ LLM API调用失败：{str(e)}")
            return None


# 全局实例（供DefectDetector直接调用，避免重复初始化）
deepseek_client = DeepSeekInterface()