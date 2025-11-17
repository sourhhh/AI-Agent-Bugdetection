from typing import List, Dict
from dataclasses import dataclass, field
from .base_schema import BaseSchema


# @dataclass
# class FixResult(BaseSchema):
#     file_path: str
#     original_code: str
#     fixed_code: str
#     strategy_used: str
#     changes_made: List[str] = field(default_factory=list)
#     confidence: float = 0.8

@dataclass
class FixResult(BaseSchema):
    file_path: str
    original_code: str
    fixed_code: str
    strategy_used: str
    changes_made: List[str] = field(default_factory=list)
    confidence: float = 0.8
    comparison: Dict = field(default_factory=dict)  # 新增对比信息
    validation: Dict = field(default_factory=dict)  # 新增验证信息
