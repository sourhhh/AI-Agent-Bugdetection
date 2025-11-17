# utils/rule_based_fixer.py
import re
import logging
from typing import Tuple, List, Dict

logger = logging.getLogger(__name__)


class RuleBasedFixer:
    """规则基础修复器 - 用于AI失败时的回退"""

    @staticmethod
    def fix_import_issues(code: str, defect_message: str) -> Tuple[str, List[str]]:
        """修复导入问题"""
        changes = []
        lines = code.split('\n')

        # 提取模块名
        module_match = re.search(r"Unable to import '([^']+)'", defect_message)
        if module_match:
            module_name = module_match.group(1)

            # 检查是否已经导入
            if not any(f"import {module_name}" in line or f"from {module_name}" in line for line in lines):
                # 添加导入
                import_line = f"import {module_name}"
                lines.insert(0, import_line)
                changes.append(f"添加导入: {module_name}")

        return '\n'.join(lines), changes

    @staticmethod
    def fix_typo_issues(code: str, defect_message: str, line_number: int) -> Tuple[str, List[str]]:
        """修复拼写错误"""
        changes = []
        lines = code.split('\n')

        if 0 < line_number <= len(lines):
            line_index = line_number - 1
            line = lines[line_index]

            # 常见拼写错误修复
            typo_fixes = {
                'prek': 'pre-commit',
                'commmit': 'commit',
                'improt': 'import',
                'funtion': 'function',
                'recieve': 'receive'
            }

            for wrong, correct in typo_fixes.items():
                if wrong in line:
                    lines[line_index] = line.replace(wrong, correct)
                    changes.append(f"修复拼写: {wrong} -> {correct}")
                    break

        return '\n'.join(lines), changes

    @staticmethod
    def fix_hardcoded_secrets(code: str, line_number: int) -> Tuple[str, List[str]]:
        """修复硬编码密码"""
        changes = []
        lines = code.split('\n')

        if 0 < line_number <= len(lines):
            line_index = line_number - 1
            line = lines[line_index]

            # 简单的硬编码密码检测和修复
            secret_patterns = [
                (r'(\w+)\s*=\s*["\'][^"\']*password[^"\']*["\']', 'password'),
                (r'(\w+)\s*=\s*["\'][^"\']*secret[^"\']*["\']', 'secret'),
                (r'(\w+)\s*=\s*["\'][^"\']*key[^"\']*["\']', 'key'),
            ]

            for pattern, secret_type in secret_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    var_name = match.group(1)
                    # 替换为环境变量
                    new_line = re.sub(
                        r'=\s*["\'][^"\']*["\']',
                        f'= os.getenv("{var_name.upper()}_SECRET")',
                        line
                    )
                    lines[line_index] = new_line
                    changes.append(f"将硬编码{secret_type}替换为环境变量")

                    # 确保导入了os
                    if not any('import os' in line for line in lines):
                        lines.insert(0, 'import os')

        return '\n'.join(lines), changes