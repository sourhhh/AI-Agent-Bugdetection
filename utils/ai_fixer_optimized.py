import requests
import json
import time
import os
import re
from typing import Dict
import logging

logger = logging.getLogger(__name__)


class AIFixerEngine:
    def __init__(self):
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        self.api_url = "https://api.deepseek.com/chat/completions"
        self.max_retries = 2
        self.timeout = 15
        self.total_calls = 0

    def is_available(self) -> bool:
        """检查AI修复引擎是否可用"""
        return bool(self.api_key)

    def extract_pure_code(self, ai_response: str, language: str = "python") -> str:
        """从AI回复中提取纯净的代码"""
        if not ai_response:
            return ""

        text = ai_response.strip()

        # 处理代码块格式
        if '```' in text:
            code_blocks = re.findall(r'```(?:\w+)?\s*(.*?)```', text, re.DOTALL)
            if code_blocks:
                code = code_blocks[-1].strip()
                # 移除可能的语言标识行
                lines = code.split('\n')
                if len(lines) > 1:
                    first_line = lines[0].strip().lower()
                    # 检查是否是语言标识
                    if first_line in ['python', 'py', 'cpp', 'c++', 'c']:
                        return '\n'.join(lines[1:]).strip()
                return code

        return text

    def _build_python_prompt(self, problem_code: str, error_info: str, context_code: str) -> str:
        """构建Python修复提示词"""
        if len(problem_code) > 1500:
            problem_code = problem_code[:1500] + "\n# ... (代码过长，已截断)"

        prompt = f"""请修复以下Python代码中的安全问题，同时确保不破坏原有功能：

安全问题：{error_info}

需要修复的代码：
```python
{problem_code}
重要要求：

1.必须保持原有功能完整，不能删除必要的代码行

2.对于随机数安全问题，使用 import secrets 替代 random 模块

3.对于SQL注入问题，使用参数化查询而不是字符串格式化

4.只返回修复后的完整代码，不要任何解释

5.使用Markdown代码块包裹修复后的代码

6.确保修复后的代码语法正确且能够运行

7.请直接返回修复后的完整代码："""
        return prompt

    def _build_cpp_prompt(self, problem_code: str, error_info: str, context_code: str) -> str:
        """构建C++修复提示词"""
        if len(problem_code) > 1500:
            problem_code = problem_code[:1500] + "\n// ... (代码过长，已截断)"

        prompt = f"""请修复以下C++代码中的问题：
        问题描述: {error_info}

        需要修复的代码:
        {problem_code}
        修复要求:

        1.保持原有功能完整

        2.确保修复后的代码符合C++最佳实践

        3.对于Qt相关代码，遵循Qt的编程规范

        4.对于内存管理问题，优先使用智能指针或正确的父子对象关系

        5.只返回修复后的完整代码，不要任何解释

        6.使用Markdown代码块包裹修复后的代码

        7.请直接返回修复后的C++代码："""
        return prompt

    def fix_with_ai(self, problem_code: str, error_info: str, context_code: str = "", language: str = "auto") -> Dict:
        """
        AI代码修复引擎 - 支持多种语言
        """
        if not self.is_available():
            return {
                "success": False,
                "fixed_code": problem_code,
                "error_message": "AI修复引擎不可用",
                "original_code": problem_code
            }

        logger.info(f"开始AI修复，问题: {error_info[:100]}...，语言: {language}")
        logger.debug(f"原始代码长度: {len(problem_code)}")

        # 自动检测语言（如果未指定）
        if language == "auto":
            language = self._detect_language(problem_code)
            logger.info(f"自动检测到语言: {language}")

        # 检查API调用频率
        self.total_calls += 1
        if self.total_calls % 5 == 0:
            time.sleep(2)

        # 构建针对不同语言的提示词
        if language == "cpp":
            prompt = self._build_cpp_prompt(problem_code, error_info, context_code)
        else:
            prompt = self._build_python_prompt(problem_code, error_info, context_code)

        # 准备API请求数据
        data = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 2000,
            "stream": False
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # 重试机制
        for attempt in range(self.max_retries):
            try:
                logger.info(f"AI修复尝试 {attempt + 1}/{self.max_retries} - 语言: {language}")

                response = requests.post(
                    self.api_url,
                    headers=headers,
                    json=data,
                    timeout=(10, 30)
                )

                if response.status_code == 200:
                    response_data = response.json()
                    ai_response = response_data['choices'][0]['message']['content']

                    fixed_code = self.extract_pure_code(ai_response, language)

                    # 验证修复结果
                    if (fixed_code and
                            fixed_code != problem_code and
                            len(fixed_code.strip()) > 10 and
                            "```" not in fixed_code):
                        logger.info("AI修复成功")
                        logger.info(f"AI修复成功，返回代码长度: {len(fixed_code)}")
                        return {
                            "success": True,
                            "fixed_code": fixed_code,
                            "error_message": None,
                            "original_code": problem_code
                        }
                    else:
                        logger.warning("AI返回的代码无效或与原始代码相同")
                        continue

                elif response.status_code == 429:
                    wait_time = (attempt + 1) * 3
                    logger.warning(f"频率限制，等待{wait_time}秒")
                    time.sleep(wait_time)
                    continue

                else:
                    logger.error(f"API错误: {response.status_code}")
                    if attempt < self.max_retries - 1:
                        time.sleep(2)
                    continue

            except requests.exceptions.Timeout:
                logger.warning(f"请求超时 (尝试 {attempt + 1})")
                if attempt < self.max_retries - 1:
                    time.sleep(5)
                continue

            except requests.exceptions.ConnectionError:
                logger.warning(f"连接错误 (尝试 {attempt + 1})")
                if attempt < self.max_retries - 1:
                    time.sleep(3)
                continue

            except Exception as e:
                logger.error(f"请求异常: {str(e)}")
                if attempt < self.max_retries - 1:
                    time.sleep(2)
                continue

        logger.error("所有AI修复尝试均失败")
        return {
            "success": False,
            "fixed_code": problem_code,
            "error_message": "所有重试尝试均失败",
            "original_code": problem_code
        }

    def _detect_language(self, code: str) -> str:
        """自动检测代码语言"""
        cpp_keywords = ['#include', 'using namespace', 'class ', 'struct ', 'public:', 'private:', 'cout <<', 'endl;']
        python_keywords = ['def ', 'import ', 'from ', 'class ', 'print(', 'lambda ']

        cpp_count = sum(1 for keyword in cpp_keywords if keyword in code)
        python_count = sum(1 for keyword in python_keywords if keyword in code)

        if cpp_count > python_count:
            return "cpp"
        else:
            return "python"

ai_fixer = AIFixerEngine()