import os
import glob
from typing import List, Optional
from dataclasses import asdict
from schemas.project_context import ProjectContext


class ProjectAnalyst:
    """项目分析器：生成标准化ProjectContext供B角色使用"""

    def __init__(self):
        # 关键识别规则（贴合Python项目规范）
        self.ENTRY_MARKER = "__name__ == \"__main__\""  # 入口文件标记
        self.REQUIREMENTS = "requirements.txt"  # 依赖文件名
        self.TEST_KEYWORDS = ["tests", "test"]  # 测试目录关键词
        self.PY_PATTERN = "**/*.py"  # Python文件匹配规则

    def analyze(self, project_root: str) -> str:
        """输入项目根目录，输出ProjectContext JSON"""
        # 1. 校验根目录合法性
        if not os.path.isdir(project_root):
            raise ValueError(f"❌ 项目目录不存在：{project_root}")

        # 2. 核心信息解析
        python_files = self._get_all_py_files(project_root)
        test_dirs = self._get_test_dirs(project_root)
        req_path, dependencies = self._parse_requirements(project_root)
        entry_points = self._get_entry_files(python_files)

        # 3. 构造接口对象
        context = ProjectContext(
            project_root=project_root,
            python_files=python_files,
            test_directories=test_dirs,
            dependencies=dependencies,
            entry_points=entry_points,
            requirements_path=req_path
        )
        return context.to_json()

    def _get_all_py_files(self, root: str) -> List[str]:
        """递归获取所有Python文件的绝对路径"""
        pattern = os.path.join(root, self.PY_PATTERN)
        return [os.path.abspath(f) for f in glob.glob(pattern, recursive=True)]

    def _get_test_dirs(self, root: str) -> List[str]:
        """识别含测试关键词的目录"""
        test_dirs = []
        for dir_root, dirs, _ in os.walk(root):
            for d in dirs:
                if any(kw.lower() in d.lower() for kw in self.TEST_KEYWORDS):
                    test_dirs.append(os.path.abspath(os.path.join(dir_root, d)))
        return list(set(test_dirs))  # 去重

    def _parse_requirements(self, root: str) -> (Optional[str], List[str]):
        """解析依赖文件，返回文件路径和依赖列表（仅保留包名）"""
        req_path = os.path.join(root, self.REQUIREMENTS)
        dependencies = []
        if os.path.exists(req_path):
            with open(req_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith(("#", "-e", "git+")):
                        dependencies.append(line.split("==")[0])
        return req_path if os.path.exists(req_path) else None, dependencies

    def _get_entry_files(self, py_files: List[str]) -> List[str]:
        """识别含__main__的入口文件"""
        entries = []
        for f in py_files:
            try:
                with open(f, "r", encoding="utf-8") as file:
                    if self.ENTRY_MARKER in file.read().replace(" ", ""):
                        entries.append(f)
            except Exception as e:
                print(f"⚠️  跳过文件：{f} → {str(e)}")
        return entries