# -*- coding: utf-8 -*-
import os
import json
from pathlib import Path
from typing import List, Set, Optional, Dict, Any
from .deepseek import DeepSeekClient
from agentcode.schemas.project_context import ProjectContext
from agentcode.utils.parsers import parse_requirements

# 支持的文件类型（Python + QT）
SUPPORTED_EXTENSIONS = {
    ".py", ".pyw",      # Python
    ".ui", ".qrc", ".qml", ".h", ".hpp", ".cpp", ".pro", ".pri", ".ts", ".qm"  # QT
}

# 排除的目录
EXCLUDE_DIRS = {".git", "__pycache__", "venv", ".venv", ".mypy_cache", ".pytest_cache", "build", "dist"}

# 入口文件（识别程序启动点）
ENTRY_POINT_FILENAMES = {"main.py", "app.py", "run.py", "mainwindow.py", "main.cpp", "mainwindow.cpp"}


class ProjectAnalyst:
    """项目分析器，支持 Python / QT 混合项目结构识别"""

    def __init__(self, project_path: str, use_deepseek: bool = False):
        self.project_path = Path(project_path).resolve()
        self.use_deepseek = use_deepseek
        self.deepseek = DeepSeekClient() if use_deepseek else None

        # 初始化属性
        self.all_files: List[str] = []
        self.python_files: List[str] = []
        self.qt_files: List[str] = []
        self.entry_points: List[str] = []
        self.test_directories: List[str] = []
        self.dependencies: List[str] = []
        self.requirements_path: Optional[str] = None
        self.project_root: str = str(self.project_path)

    # ============================================================
    # 文件收集逻辑
    # ============================================================

    def collect_project_files(self) -> None:
        """扫描项目路径下所有支持的文件"""
        print(f"[分析器] 开始扫描项目路径：{self.project_path}")
        qt_extensions = {".ui", ".qrc", ".qml", ".h", ".hpp", ".cpp", ".pro", ".pri", ".ts", ".qm"}

        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            current_dir = Path(root)

            # 检测测试目录
            if 'test' in str(current_dir).lower() and str(current_dir) not in self.test_directories:
                self.test_directories.append(str(current_dir))

            for file in files:
                file_path = current_dir / file
                rel_path = str(file_path.relative_to(self.project_path))
                ext = file_path.suffix.lower()

                # QT文件
                if ext in qt_extensions:
                    self.qt_files.append(rel_path)
                    self.all_files.append(rel_path)
                    if file in ENTRY_POINT_FILENAMES:
                        self.entry_points.append(rel_path)

                # Python文件
                elif ext in (".py", ".pyw"):
                    self.python_files.append(rel_path)
                    self.all_files.append(rel_path)
                    if file in ENTRY_POINT_FILENAMES:
                        self.entry_points.append(rel_path)

            # 依赖文件检测
            if not self.requirements_path:
                for req in ["requirements.txt", "pyproject.toml", "Pipfile"]:
                    if req in files:
                        self.requirements_path = str(current_dir / req)
                        break

        print(f"[分析器] 文件扫描完成：共 {len(self.all_files)} 个文件")
        print(f" - Python 文件: {len(self.python_files)}")
        print(f" - QT 文件: {len(self.qt_files)}")
        print(f" - 入口文件: {len(self.entry_points)}")
        if self.requirements_path:
            print(f" - 依赖文件: {self.requirements_path}")

    # ============================================================
    # 文件内容读取（QT 项目分析增强）
    # ============================================================

    def read_qt_file_contents(self, files: List[str], max_size: int = 2000) -> Dict[str, str]:
        """读取QT文件内容（部分截断）"""
        contents = {}
        for rel_path in files:
            abs_path = self.project_path / rel_path
            try:
                if abs_path.exists() and abs_path.is_file():
                    with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                        code = f.read()
                        contents[rel_path] = code[:max_size]
                else:
                    contents[rel_path] = "[文件不存在或无法访问]"
            except Exception as e:
                contents[rel_path] = f"[读取失败: {e}]"
        return contents

    # ============================================================
    # 上下文对象创建
    # ============================================================

    def create_project_context(self) -> ProjectContext:
        """创建项目上下文（兼容旧结构）"""
        return ProjectContext(
            project_root=self.project_root,
            python_files=self.python_files,
            test_directories=self.test_directories,
            dependencies=self.dependencies,
            entry_points=self.entry_points,
            requirements_path=self.requirements_path
        )

    # ============================================================
    # 主分析逻辑
    # ============================================================

    def analyze(self) -> Dict[str, Any]:
        """执行项目分析流程"""
        self.collect_project_files()
        project_context = self.create_project_context()

        # 基础结果结构
        result = {
            "project_context": project_context.to_json(),
            "raw_analysis": {"modules": {}}
        }

        # 如果不使用 DeepSeek，只做静态收集
        if not self.use_deepseek or not self.deepseek:
            print("[分析器] 未启用 DeepSeek，返回文件结构信息。")
            return result

        print("[分析器] 启用 DeepSeek 分析中...")

        # ========== Step 1: 读取 QT 文件内容 ==========
        qt_file_contents = self.read_qt_file_contents(self.qt_files)

        # ========== Step 2: 调用 DeepSeek 的结构识别 ==========
        print("[分析器] 调用 DeepSeek.generate_raw_analysis() ...")
        raw_analysis = self.deepseek.generate_raw_analysis({
            "python_files": [str(self.project_path / f) for f in self.python_files],
            "qt_files": [str(self.project_path / f) for f in self.qt_files],
        })
        result["raw_analysis"] = raw_analysis

        # 深度项目分析 
        print("[分析器] 调用 DeepSeek.analyze_project() ...")
        deepseek_result = self.deepseek.analyze_project({
            "project_root": self.project_root,
            "all_files": [str(self.project_path / f) for f in self.all_files],
            "python_files": [str(self.project_path / f) for f in self.python_files],
            "qt_files": [str(self.project_path / f) for f in self.qt_files],
            "entry_points": [str(self.project_path / f) for f in self.entry_points],
            "test_directories": [str(self.project_path / f) for f in self.test_directories],
            "dependencies": self.dependencies,
        })
        result["deepseek_analysis"] = deepseek_result

        print("[分析器] DeepSeek 项目分析完成。")
        return result
