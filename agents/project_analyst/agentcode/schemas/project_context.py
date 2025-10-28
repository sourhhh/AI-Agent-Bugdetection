from typing import List, Optional
from dataclasses import dataclass, asdict
import json

@dataclass
class ProjectContext:
    project_root: str
    python_files: List[str]          # 所有Python文件的绝对路径列表
    test_directories: List[str]      # 测试目录的绝对路径列表
    dependencies: List[str]          # 项目依赖包列表
    entry_points: List[str]          # 项目入口文件（如main.py）
    requirements_path: Optional[str] # requirements.txt的路径

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'ProjectContext':
        data = json.loads(json_str)
        return cls(** data)