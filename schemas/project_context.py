# schemas/project_context.py
from typing import List, Optional
from dataclasses import dataclass, asdict, field
import json


@dataclass
class ProjectContext:
    """
    项目上下文数据类（接口标准化协议定义）
    作为DefectDetector的输入，包含待检测文件、项目根目录等信息
    """
    project_root: str  # 项目根目录绝对路径
    python_files: List[str] = field(default_factory=list)  # 所有待检测Python文件的路径列表
    test_directories: List[str] = field(default_factory=list)  # 测试目录列表
    dependencies: List[str] = field(default_factory=list)  # 项目依赖列表
    entry_points: List[str] = field(default_factory=list)  # 项目入口文件列表
    requirements_path: Optional[str] = None  # requirements.txt路径

    # 新增语言相关文件列表以兼容多语言项目
    java_files: List[str] = field(default_factory=list)
    qt_files: List[str] = field(default_factory=list)
    c_files: List[str] = field(default_factory=list)
    cpp_files: List[str] = field(default_factory=list)

    def to_json(self) -> str:
        """转换为JSON字符串（用于Agent间数据传递）"""
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> 'ProjectContext':
        """从JSON字符串或 dict 反序列化为对象（兼容旧格式，缺失字段使用默认值）"""
        if isinstance(json_str, dict):
            data = json_str
        else:
            data = json.loads(json_str)

        allowed_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in allowed_keys}
        return cls(**filtered)

    @property
    def pure_python_files(self):
        """返回仅包含 .py 后缀的 Python 文件列表（兼容旧代码）"""
        return [f for f in (self.python_files or []) if f.endswith('.py')]
