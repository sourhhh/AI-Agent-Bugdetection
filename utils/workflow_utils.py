import datetime
import json
import os
from typing import Dict, List


def validate_defect_report(report_path: str) -> bool:
    """验证缺陷报告文件的格式"""
    try:
        with open(report_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 基本结构验证
        required_fields = ['files', 'summary']
        if not all(field in data for field in required_fields):
            return False

        # 文件列表验证
        if not isinstance(data['files'], list):
            return False

        return True

    except Exception:
        return False


def backup_original_files(repair_plan, backup_dir="backup"):
    """备份原始文件"""
    os.makedirs(backup_dir, exist_ok=True)

    for task in repair_plan.tasks:
        if os.path.exists(task.file_path):
            import shutil
            backup_path = os.path.join(backup_dir, os.path.basename(task.file_path))
            shutil.copy2(task.file_path, backup_path)


def create_repair_report(repair_summary: Dict, output_path: str):
    """创建详细的修复报告"""
    report = {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total_tasks": repair_summary['total_tasks'],
            "successful_repairs": repair_summary['successful_repairs'],
            "failed_repairs": repair_summary['failed_repairs'],
            "success_rate": repair_summary['success_rate']
        },
        "detailed_results": repair_summary['repair_results']
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)