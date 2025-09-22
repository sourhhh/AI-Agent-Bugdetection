# schemas/defect_report.py
from typing import List, Dict, Literal
from dataclasses import dataclass, field, asdict
import json


@dataclass
class Defect:
    """单个缺陷数据类（接口标准化协议定义）"""
    type: Literal["syntax", "security", "logic", "performance", "code_smell"]
    message: str
    line_number: int
    severity: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    tool: Literal["pylint", "bandit", "llm", "mypy"]
    confidence: float = 0.8

    # 新增：Defect的反序列化方法
    @classmethod
    def from_json(cls, data: dict) -> 'Defect':
        return cls(**data)


@dataclass
class FileDefects:
    """单个文件的缺陷集合（接口标准化协议定义）"""
    file_path: str
    defects: List[Defect] = field(default_factory=list)

    # 新增：FileDefects的反序列化方法（处理嵌套的Defect）
    @classmethod
    def from_json(cls, data: dict) -> 'FileDefects':
        # 将defects字典列表转换为Defect对象列表
        defects = [Defect.from_json(d) for d in data.get("defects", [])]
        return cls(
            file_path=data.get("file_path", ""),
            defects=defects
        )


@dataclass
class DefectReport:
    """完整缺陷报告数据类（接口标准化协议定义）"""
    files: List[FileDefects] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)

    # 修复：DefectReport的反序列化方法（处理嵌套的FileDefects）
    @classmethod
    def from_json(cls, json_str: str) -> 'DefectReport':
        data = json.loads(json_str)
        # 将files字典列表转换为FileDefects对象列表（核心修复）
        files = [FileDefects.from_json(f) for f in data.get("files", [])]
        return cls(
            files=files,
            summary=data.get("summary", {})
        )