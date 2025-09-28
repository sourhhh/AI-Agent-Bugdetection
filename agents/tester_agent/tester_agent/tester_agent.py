import subprocess
import json
import os
from .deepseek_client import DeepSeekClient
from .config_loader import ConfigLoader

class TesterAgent:
    def __init__(self, config_path="config.json"):
        # 加载配置文件
        self.config = ConfigLoader(config_path).load_config()
        # 初始化 DeepSeek 客户端
        self.deepseek = DeepSeekClient(self.config)

    def run_tests(self, code_dir: str, test_dir: str) -> dict:
        """
        执行 pytest 测试并返回结果
        """
        try:
            cmd = [
                "pytest",
                test_dir,
                "--maxfail=1",        # 遇到首个失败就停止
                "--disable-warnings",
                "--cov=" + code_dir,  # 覆盖率
                "-q"
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            passed = (result.returncode == 0)
            output_log = result.stdout + "\n" + result.stderr

            # DeepSeek AI 总结测试结果
            summary = self.deepseek.analyze_code_chunk(output_log)

            return {
                "passed": passed,
                "output": output_log,
                "coverage": self._extract_coverage(output_log),
                "deepseek_summary": summary
            }

        except Exception as e:
            return {
                "passed": False,
                "output": str(e),
                "coverage": "0%",
                "deepseek_summary": "测试执行失败，未能调用 deepseek。"
            }

    def _extract_coverage(self, output: str) -> str:
        """
        提取覆盖率信息
        """
        for line in output.splitlines():
            if "%" in line and ("cov" in line.lower() or "coverage" in line.lower()):
                return line.split()[-1]
        return "N/A"
