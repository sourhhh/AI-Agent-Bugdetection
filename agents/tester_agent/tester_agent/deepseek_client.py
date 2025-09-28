import requests
import textwrap

class DeepSeekClient:
    def __init__(self, config: dict):
        """
        初始化 DeepSeek 客户端
        :param config: 从 config_loader 读取的配置
        """
        self.api_key = config.get("deepseek_api_key", "sk-c340dc402a624d99a04dc0865da97eda")
        self.model = config.get("model", "deepseek-chat")
        self.chunk_size = config.get("chunk_size", 2000)
        self.timeout = config.get("timeout", 60)
        self.base_url = config.get("base_url", "https://api.deepseek.com/chat/completions")

    def analyze_code_chunk(self, code_chunk: str) -> str:
        """
        分析单个代码或日志片段
        :param code_chunk: 输入的代码/日志
        :return: DeepSeek AI 的总结
        """
        if not self.api_key:
            return "⚠️ 未设置 DeepSeek API Key，无法调用 AI。"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是一个软件分析助手，帮助总结代码或测试日志。"},
                {"role": "user", "content": code_chunk}
            ]
        }

        try:
            response = requests.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            return f"⚠️ DeepSeek API 调用失败: {e}"

    def analyze_large_project(self, code: str) -> str:
        """
        支持大规模项目分块上传分析
        :param code: 整个项目的代码字符串
        :return: DeepSeek AI 分析总结
        """
        chunks = textwrap.wrap(code, self.chunk_size)
        summaries = []

        for i, chunk in enumerate(chunks, start=1):
            summary = self.analyze_code_chunk(f"【第 {i} 部分】\n{chunk}")
            summaries.append(summary)

        # 将所有小结再汇总成一个总的结论
        final_summary = self.analyze_code_chunk(
            "以下是项目分块分析结果，请总结成一个整体结论：\n" + "\n".join(summaries)
        )
        return final_summary
