import json
from dataclasses import dataclass
from typing import List


@dataclass
class BatchConfig:
    """批量处理配置"""
    # 缺陷过滤
    min_severity: str = "MEDIUM"  # CRITICAL, HIGH, MEDIUM, LOW
    max_files_per_batch: int = 50
    max_defects_per_file: int = 20

    # 执行配置
    max_workers: int = 3
    timeout_per_task: int = 30
    retry_attempts: int = 2

    # 输出配置
    save_fixed_files: bool = True
    generate_reports: bool = True
    backup_original: bool = True


def create_batch_configs():
    """创建不同的批量处理配置"""
    configs = {
        "fast": BatchConfig(
            min_severity="HIGH",
            max_workers=2,
            max_files_per_batch=20
        ),
        "balanced": BatchConfig(
            min_severity="MEDIUM",
            max_workers=3,
            max_files_per_batch=50
        ),
        "comprehensive": BatchConfig(
            min_severity="LOW",
            max_workers=4,
            max_files_per_batch=100
        )
    }
    return configs