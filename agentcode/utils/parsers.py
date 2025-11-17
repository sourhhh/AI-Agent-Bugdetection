# -*- coding: utf-8 -*-
from pathlib import Path
from typing import List
try:
    import tomllib  # Python 3.11+
except Exception:
    try:
        import tomli as tomllib  # type: ignore  # backport for older Pythons
    except Exception:
        tomllib = None  # type: ignore


def parse_requirements(project_path: Path) -> List[str]:
    """解析项目依赖文件（requirements.txt/pyproject.toml/Pipfile）"""
    requirements: List[str] = []

    # 优先解析requirements.txt
    req_file = project_path / "requirements.txt"
    if req_file.exists():
        with open(req_file, "r", encoding="utf-8") as f:
            requirements = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    
    # 解析pyproject.toml (PEP 621标准)
    elif (project_path / "pyproject.toml").exists():
        toml_file = project_path / "pyproject.toml"
        with open(toml_file, "rb") as f:
            if tomllib is None:
                requirements.append("无法解析pyproject.toml：缺少 tomllib/tomli 依赖")
            else:
                try:
                    data = tomllib.load(f)
                    # 提取dependencies部分
                    if "project" in data and "dependencies" in data["project"]:
                        requirements = data["project"]["dependencies"]
                    else:
                        requirements.append("pyproject.toml中未找到dependencies配置")
                except Exception as e:
                    requirements.append(f"解析pyproject.toml失败: {str(e)}")
    
    # 标记Pipfile（简单支持）
    elif (project_path / "Pipfile").exists():
        requirements.append("检测到Pipfile（支持计划中）")

    return requirements