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

    @staticmethod
    def fix_random_usage(code: str) -> Tuple[str, List[str]]:
        """替换不安全的 random 用法为 secrets（安全随机）并确保导入"""
        changes = []
        lines = code.split('\n')

        replaced = False
        for i, line in enumerate(lines):
            if 'random.' in line and 'import random' in code:
                # 简单替换常见函数
                new_line = line
                if 'random.random(' in line:
                    new_line = line.replace('random.random()', 'secrets.SystemRandom().random()')
                if 'random.randint(' in line:
                    # 转换为 secrets.randbelow 接近用法（保持参数位置）
                    new_line = re.sub(r'random\.randint\(([^,]+),\s*([^\)]+)\)', r'secrets.randbelow((\2) - (\1) + 1) + (\1)', new_line)
                if 'random.choice(' in line:
                    new_line = line.replace('random.choice(', 'secrets.choice(')

                if new_line != line:
                    lines[i] = new_line
                    replaced = True
        if replaced:
            # 确保导入secrets
            if not any('import secrets' in l for l in lines):
                # 尝试在导入块后插入
                inserted = False
                for i, l in enumerate(lines):
                    if l.strip().startswith('import ') or l.strip().startswith('from '):
                        lines.insert(i + 1, 'import secrets')
                        inserted = True
                        break
                if not inserted:
                    lines.insert(0, 'import secrets')
            changes.append('替换不安全的 random 用法为 secrets')

        return '\n'.join(lines), changes

    @staticmethod
    def fix_subprocess_shell(code: str) -> Tuple[str, List[str]]:
        """将使用 shell=True 的 subprocess 调用替换为更安全的 subprocess.run + shlex.split（若可能）"""
        changes = []
        lines = code.split('\n')
        replaced = False

        for i, line in enumerate(lines):
            if 'subprocess.call' in line or 'subprocess.Popen' in line or 'subprocess.run' in line:
                # 只针对带 shell=True 的情况进行转换
                if 'shell=True' in line:
                    # 尝试把 subprocess.call(cmd, shell=True) -> subprocess.run(shlex.split(cmd), check=True)
                    new_line = line
                    # 捕获命令变量或字符串
                    new_line = new_line.replace('subprocess.call(', 'subprocess.run(')
                    new_line = new_line.replace('shell=True', 'check=True')
                    # 如果参数是一个字符串变量，建议使用 shlex.split
                    if ',' not in line or 'shell=True' in line:
                        # 向调用添加 shlex.split(...) 包裹，尝试找到第一个参数
                        new_line = re.sub(r'subprocess\.run\(([^,\)]+)', r'subprocess.run(shlex.split(\1)', new_line)

                    if new_line != line:
                        lines[i] = new_line
                        replaced = True

        if replaced:
            # 确保导入 shlex 和 subprocess
            has_shlex = any('import shlex' in l for l in lines)
            has_subp = any('import subprocess' in l for l in lines)
            if not has_shlex:
                # 插入到导入块
                inserted = False
                for i, l in enumerate(lines):
                    if l.strip().startswith('import ') or l.strip().startswith('from '):
                        lines.insert(i + 1, 'import shlex')
                        inserted = True
                        break
                if not inserted:
                    lines.insert(0, 'import shlex')
            if not has_subp:
                inserted = False
                for i, l in enumerate(lines):
                    if l.strip().startswith('import ') or l.strip().startswith('from '):
                        lines.insert(i + 1, 'import subprocess')
                        inserted = True
                        break
                if not inserted:
                    lines.insert(0, 'import subprocess')

            changes.append('将 subprocess 的 shell=True 调用替换为更安全的调用并添加 shlex')

        return '\n'.join(lines), changes

    @staticmethod
    def fix_os_system_usage(code: str) -> Tuple[str, List[str]]:
        """将使用 os.system 的调用替换为更安全的 subprocess.run(shlex.split(...)) 并确保导入"""
        changes = []
        lines = code.split('\n')
        replaced = False

        for i, line in enumerate(lines):
            if 'os.system(' in line:
                # 简单将 os.system("cmd") -> subprocess.run(shlex.split("cmd"), check=True)
                new_line = line.replace('os.system(', 'subprocess.run(shlex.split(')
                # 把可能的 .read() 移除
                new_line = new_line.replace('.read()', '')
                if new_line != line:
                    lines[i] = new_line
                    replaced = True

        if replaced:
            # 确保导入了 subprocess 和 shlex
            has_shlex = any('import shlex' in l for l in lines)
            has_subp = any('import subprocess' in l for l in lines)
            has_os = any('import os' in l for l in lines)
            insert_at = 0
            for i, l in enumerate(lines):
                if l.strip().startswith('import ') or l.strip().startswith('from '):
                    insert_at = i
                    break
            if not has_shlex:
                lines.insert(insert_at + 1, 'import shlex')
            if not has_subp:
                lines.insert(insert_at + 1, 'import subprocess')
            # 保留 os 导入（如果存在），不要移除
            changes.append('将 os.system 调用替换为 subprocess.run(shlex.split(...))')

        return '\n'.join(lines), changes

    @staticmethod
    def fix_import_typos(code: str) -> Tuple[str, List[str]]:
        """修复常见的导入拼写错误（低风险替换）"""
        changes = []
        lines = code.split('\n')
        typo_map = {
            'improt ': 'import ',
            'from os import paht': 'from os import path',
            'import Json': 'import json',
        }
        replaced = False
        for i, line in enumerate(lines):
            for wrong, right in typo_map.items():
                if wrong in line:
                    lines[i] = line.replace(wrong, right)
                    changes.append(f"修复导入拼写: '{wrong.strip()}' -> '{right.strip()}'")
                    replaced = True
                    break

        return '\n'.join(lines), changes