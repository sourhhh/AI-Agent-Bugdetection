"""Compatibility shim: delegate to CodeQualityEvaluator.

This module kept for backward compatibility with older scripts
that import `RepairEvaluator`. It wraps the richer
`CodeQualityEvaluator` implementation so callers keep working.
"""

import os
from typing import List
from agents.code_quality_evaluator import CodeQualityEvaluator


class RepairEvaluator:
    def __init__(self, run_dir: str):
        # try to find a repair report JSON under run_dir
        pattern = os.path.join(run_dir, '**', '*_repair_report_*.json')
        import glob
        files = glob.glob(pattern, recursive=True)
        if not files:
            files = glob.glob(os.path.join(run_dir, '**', '*.json'), recursive=True)
        if not files:
            raise FileNotFoundError('未找到 repair report json in run_dir')
        self.report_path = files[0]
        self._delegate = CodeQualityEvaluator(self.report_path)
        self.results: List[dict] = []

    def discover_reports(self):
        # kept for compatibility (no-op)
        return

    def load_reports(self):
        self._delegate.load_report()
        self.results = self._delegate.results

    def analyze_each(self):
        # code quality evaluator already computes metrics during generate_html
        return

    def generate_html(self, out_path: str):
        return self._delegate.generate_html(out_path)

