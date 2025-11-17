from typing import List, Dict

# Python 3.7 兼容性处理
try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal
from dataclasses import dataclass, field
from .base_schema import BaseSchema
import json


@dataclass
class RepairTask(BaseSchema):
    file_path: str
    defect_index: int
    strategy: str
    priority: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    context: Dict = field(default_factory=dict)


@dataclass
class RepairPlan(BaseSchema):
    tasks: List[RepairTask] = field(default_factory=list)
    total_tasks: int = 0

    @classmethod
    def from_json(cls, json_str: str):
        """从JSON字符串创建对象"""
        data = json.loads(json_str)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> 'RepairPlan':
        """从字典创建RepairPlan对象"""
        tasks = []
        for task_data in data.get('tasks', []):
            # 确保context字段存在
            task_data.setdefault('context', {})
            # 创建RepairTask对象
            task = RepairTask(
                file_path=task_data['file_path'],
                defect_index=task_data['defect_index'],
                strategy=task_data['strategy'],
                priority=task_data['priority'],
                context=task_data['context']
            )
            tasks.append(task)

        return cls(
            tasks=tasks,
            total_tasks=data.get('total_tasks', len(tasks))
        )