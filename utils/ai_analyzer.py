import requests
import json
import time
import os
import re
from typing import Dict, Optional, List
import logging

logger = logging.getLogger(__name__)


class AIAnalyzerEngine:
    """AI分析引擎 - 专门用于决策分析，不是代码修复"""

    def __init__(self):
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        self.api_url = "https://api.deepseek.com/chat/completions"
        self.max_retries = 3
        self.timeout = 30

    def is_available(self) -> bool:
        """检查AI分析引擎是否可用"""
        return bool(self.api_key)

    def analyze_defect_priority(self, defect_type: str, defect_message: str, severity: str, line_number: int) -> str:
        """
        分析缺陷优先级 - 专门为Decision Manager设计
        """
        if not self.is_available():
            return self._get_default_priority(defect_type)

        prompt = f"""
你是一个代码质量专家，需要评估代码缺陷的修复优先级。

缺陷信息：
- 类型：{defect_type}
- 描述：{defect_message}
- 严重程度：{severity}
- 位置：第{line_number}行

请根据以下标准评估修复优先级：
1. CRITICAL：安全漏洞、系统崩溃、数据丢失等严重问题
2. HIGH：功能错误、语法错误、逻辑错误等影响功能的问题  
3. MEDIUM：性能问题、代码质量问题等不影响功能但需要改进的问题
4. LOW：代码风格、注释等不影响功能和性能的问题

请只返回以下四个选项中的一个：CRITICAL, HIGH, MEDIUM, LOW
不要返回任何其他文字。
"""

        messages = [{"role": "user", "content": prompt}]

        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    self.api_url,
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json={
                        "model": "deepseek-chat",
                        "messages": messages,
                        "temperature": 0.1,
                        "max_tokens": 100
                    },
                    timeout=self.timeout
                )

                if response.status_code == 200:
                    response_data = response.json()
                    ai_response = response_data['choices'][0]['message']['content'].strip()

                    valid_priorities = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
                    if ai_response in valid_priorities:
                        return ai_response
                    else:
                        logger.warning(f"AI返回了无效的优先级: {ai_response}，使用默认规则")
                        return self._get_default_priority(defect_type)

                elif response.status_code == 429:
                    time.sleep(2)
                    continue

            except Exception as e:
                logger.warning(f"AI优先级分析失败: {e}")
                if attempt == self.max_retries - 1:
                    return self._get_default_priority(defect_type)
                time.sleep(1)

        return self._get_default_priority(defect_type)

    def suggest_repair_strategy(self, defect_type: str, defect_message: str, code_context: str = "") -> str:
        """
        建议修复策略 - 专门为Decision Manager设计
        """
        if not self.is_available():
            return self._get_default_strategy(defect_type)

        # 改进提示词，明确要求返回策略标识符
        prompt = f"""
    你是一个代码修复策略专家，需要为代码缺陷推荐合适的修复策略标识符。

    缺陷信息：
    - 类型：{defect_type}
    - 描述：{defect_message}

    可用的修复策略标识符：
    - replace_eval_with_ast_literal_eval (用于安全漏洞，特别是eval相关)
    - fix_syntax_error (用于语法错误)
    - add_null_check (用于空值检查相关的逻辑错误) 
    - fix_indentation (用于缩进问题)
    - add_type_hint (用于类型提示)
    - ai_automatic_fix (通用策略)

    请根据缺陷类型和描述，选择最合适的策略标识符。
    **重要：只返回策略标识符名称，不要返回数字、不要解释、不要其他文字。**

    示例：
    如果缺陷是安全漏洞，返回：replace_eval_with_ast_literal_eval
    如果缺陷是语法错误，返回：fix_syntax_error

    请返回策略标识符：
    """

        messages = [{"role": "user", "content": prompt}]

        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    self.api_url,
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json={
                        "model": "deepseek-chat",
                        "messages": messages,
                        "temperature": 0.1,
                        "max_tokens": 50  # 减少token数量，避免多余输出
                    },
                    timeout=self.timeout
                )

                if response.status_code == 200:
                    response_data = response.json()
                    ai_response = response_data['choices'][0]['message']['content'].strip()

                    # 更严格的验证
                    valid_strategies = {
                        "replace_eval_with_ast_literal_eval", "fix_syntax_error", "add_null_check",
                        "fix_indentation", "add_type_hint", "ai_automatic_fix"
                    }

                    # 清理响应，移除可能的标点符号和空格
                    cleaned_response = ai_response.strip().rstrip('.,!?;')

                    if cleaned_response in valid_strategies:
                        return cleaned_response
                    else:
                        logger.warning(f"AI返回了无效的策略: '{ai_response}'，使用默认策略")
                        return self._get_default_strategy(defect_type)

            except Exception as e:
                logger.warning(f"AI策略建议失败: {e}")
                if attempt == self.max_retries - 1:
                    return self._get_default_strategy(defect_type)
                time.sleep(1)

        return self._get_default_strategy(defect_type)

    def _get_default_priority(self, defect_type: str) -> str:
        """默认优先级规则"""
        priority_rules = {
            "security": "CRITICAL",
            "syntax": "HIGH",
            "logic": "HIGH",
            "performance": "MEDIUM",
            "code_smell": "LOW"
        }
        return priority_rules.get(defect_type, "MEDIUM")

    def _get_default_strategy(self, defect_type: str) -> str:
        """默认策略规则"""
        strategy_map = {
            "security": "replace_eval_with_ast_literal_eval",
            "syntax": "fix_syntax_error",
            "logic": "add_null_check",
            "performance": "ai_automatic_fix",
            "code_smell": "ai_automatic_fix"
        }
        return strategy_map.get(defect_type, "ai_automatic_fix")


# 全局实例
ai_analyzer = AIAnalyzerEngine()