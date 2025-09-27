# -*- coding: utf-8 -*-
import os
import ast
import json
from pathlib import Path
from deepseek_client import DeepSeekClient


EXCLUDE_DIRS = {".git", "__pycache__", "venv", ".venv", ".mypy_cache", ".pytest_cache"}


class ProjectAnalyst:
    def __init__(self, project_path: str, use_deepseek: bool = False):
        self.project_path = Path(project_path)
        self.use_deepseek = use_deepseek
        self.deepseek = DeepSeekClient() if use_deepseek else None

    def parse_requirements(self):
        """解析项目依赖（requirements.txt / pyproject.toml / Pipfile）"""
        requirements = []

        req_file = self.project_path / "requirements.txt"
        if req_file.exists():
            with open(req_file, "r", encoding="utf-8") as f:
                requirements = [line.strip() for line in f if line.strip()]

        elif (self.project_path / "pyproject.toml").exists():
            requirements.append("pyproject.toml detected (解析未实现)")

        elif (self.project_path / "Pipfile").exists():
            requirements.append("Pipfile detected (解析未实现)")

        return requirements

    def parse_python_file(self, file_path: Path):
        """解析 Python 文件，提取函数与类"""
        info = {"functions": [], "classes": []}
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=str(file_path))

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    info["functions"].append(node.name)
                elif isinstance(node, ast.ClassDef):
                    info["classes"].append(node.name)

        except Exception as e:
            info["error"] = str(e)

        return info

    def analyze(self):
        project_structure = {
            "requirements": self.parse_requirements(),
            "modules": {},
            "tests": [],
        }
        test_directory = None

        for root, dirs, files in os.walk(self.project_path):
            # 排除不相关目录
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

            rel_root = os.path.relpath(root, self.project_path)
            if rel_root == ".":
                rel_root = ""

            # 遍历文件
            for file in files:
                if file.endswith(".py"):
                    file_path = Path(root) / file
                    rel_path = os.path.join(rel_root, file) if rel_root else file

                    # 判断是否为测试文件
                    if file.startswith("test_") or "tests" in rel_root:
                        project_structure["tests"].append(rel_path)
                        if test_directory is None and "tests" in rel_root:
                            test_directory = rel_root
                    else:
                        project_structure["modules"][rel_path] = self.parse_python_file(file_path)

        result = {
            "project_structure": project_structure,
            "test_directory": test_directory or "tests"
        }

        # 调用 DeepSeek 进一步分析
        if self.use_deepseek and self.deepseek:
            ai_analysis = self.deepseek.analyze_project(result)
            result["deepseek_analysis"] = ai_analysis

        return result


if __name__ == "__main__":
    analyst = ProjectAnalyst("sample_project", use_deepseek=False)
    output = analyst.analyze()
    print(json.dumps(output, indent=4, ensure_ascii=False))
