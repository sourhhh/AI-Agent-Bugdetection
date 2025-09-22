# schemas/project_context.py
from typing import List, Optional
from dataclasses import dataclass, asdict
import json


@dataclass
class ProjectContext:
    """
    项目上下文数据类（接口标准化协议定义）
    作为DefectDetector的输入，包含待检测文件、项目根目录等信息
    """
    project_root: str  # 项目根目录绝对路径
    python_files: List[str]  # 所有待检测Python文件的绝对路径列表
    test_directories: List[str]  # 测试目录列表（B角色暂不使用，保留字段）
    dependencies: List[str]  # 项目依赖列表（B角色暂不使用，保留字段）
    entry_points: List[str]  # 项目入口文件列表（B角色暂不使用，保留字段）
    requirements_path: Optional[str]  # requirements.txt路径（B角色暂不使用，保留字段）

    def to_json(self) -> str:
        """转换为JSON字符串（用于Agent间数据传递）"""
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> 'ProjectContext':
        """从JSON字符串反序列化为对象（解析输入）"""
        data = json.loads(json_str)
        return cls(**data)