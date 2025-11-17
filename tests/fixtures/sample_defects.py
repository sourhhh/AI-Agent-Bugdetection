from schemas.defect_report import Defect, FileDefects, DefectReport

# 示例缺陷数据
SAMPLE_DEFECT = Defect(
    type="security",
    message="Use of insecure function 'eval'",
    line_number=42,
    severity="CRITICAL",
    tool="bandit",
    confidence=0.95
)

SAMPLE_FILE_DEFECTS = FileDefects(
    file_path="/path/to/project/utils/helpers.py",
    defects=[SAMPLE_DEFECT]
)

SAMPLE_DEFECT_REPORT = DefectReport(
    files=[SAMPLE_FILE_DEFECTS],
    summary={"CRITICAL": 1, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
)

SAMPLE_REPAIR_PLAN_DICT = {
    "tasks": [
        {
            "file_path": "/path/to/project/utils/helpers.py",
            "defect_index": 0,
            "strategy": "replace_eval_with_ast_literal_eval",
            "priority": "CRITICAL",
            "context": {
                "vulnerable_function": "eval",
                "safe_replacement": "ast.literal_eval"
            }
        }
    ],
    "total_tasks": 1
}