import json
from dataclasses import dataclass, asdict, is_dataclass
from typing import List, Dict, Optional, Any, Type, TypeVar

T = TypeVar('T', bound='BaseSchema')

@dataclass
class BaseSchema:
    def to_json(self) -> str:
        """转换为JSON字符串"""
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls: Type[T], json_str: str) -> T:
        """从JSON字符串创建对象"""
        data = json.loads(json_str)
        return cls(**data)

    @classmethod
    def from_dict(cls: Type[T], data: dict) -> T:
        """从字典创建对象"""
        return cls(**data)