from typing import List, Optional
from dataclasses import dataclass, asdict, field
import json


@dataclass
class ProjectContext:
    project_root: str
    python_files: List[str] = field(default_factory=list)          # 所有Python文件的路径列表
    test_directories: List[str] = field(default_factory=list)      # 测试目录的路径列表
    dependencies: List[str] = field(default_factory=list)          # 项目依赖包列表
    entry_points: List[str] = field(default_factory=list)          # 项目入口文件（如main.py）
    requirements_path: Optional[str] = None # requirements.txt的路径

    # 新增语言相关文件列表（兼容旧 JSON，默认空列表）
    java_files: List[str] = field(default_factory=list)
    qt_files: List[str] = field(default_factory=list)
    c_files: List[str] = field(default_factory=list)
    cpp_files: List[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> 'ProjectContext':
        # 支持传入 dict 或 JSON 字符串；对缺失字段使用默认值以保持向后兼容
        if isinstance(json_str, dict):
            data = json_str
        else:
            data = json.loads(json_str)

        # 仅保留 dataclass 接受的字段，其余忽略
        allowed_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in allowed_keys}

        return cls(**filtered)