import os
import sys
import threading
import uuid
import json
import time
import subprocess
import shutil
from typing import Dict, Any

BASE_DIR = os.path.dirname(__file__)  # backend/services_new
# adjust to backend root
PROJECT_ROOT = os.path.dirname(BASE_DIR)
OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'output')
TASKS_FILE = os.path.join(PROJECT_ROOT, '.tasks.json')

# in-memory tasks
_tasks: Dict[str, Dict[str, Any]] = {}
_tasks_lock = threading.Lock()


def _persist_tasks():
    try:
        with open(TASKS_FILE, 'w', encoding='utf-8') as f:
            json.dump(_tasks, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def _load_tasks():
    if os.path.isfile(TASKS_FILE):
        try:
            with open(TASKS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                _tasks.update(data)
        except Exception:
            pass


_load_tasks()


def _choose_python_exec():
    # prefer .venv in project root
    venv_py = os.path.join(PROJECT_ROOT, '.venv', 'Scripts', 'python.exe')
    if os.path.isfile(venv_py):
        return venv_py
    return sys.executable


def _write_log(task_id: str, text: str):
    out_dir = os.path.join(OUTPUT_DIR, task_id)
    os.makedirs(out_dir, exist_ok=True)
    log_path = os.path.join(out_dir, 'pipeline.log')
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(text + '\n')


def start_pipeline(options: Dict[str, Any] = None) -> str:
    """
    启动一个后台任务来执行分析->检测->修复->质量评估流程。
    返回 task_id。
    options 可含: use_deepseek (bool), extra args
    """
    options = options or {}
    task_id = str(uuid.uuid4())
    out_dir = os.path.join(OUTPUT_DIR, task_id)
    os.makedirs(out_dir, exist_ok=True)

    task = {
        'id': task_id,
        'status': 'pending',
        'stage': None,
        'progress': 0,
        'started_at': time.time(),
        'finished_at': None,
        'output_dir': out_dir,
        'artifacts': {},
        'last_message': ''
    }

    with _tasks_lock:
        _tasks[task_id] = task
        _persist_tasks()

    t = threading.Thread(target=_run_pipeline_thread, args=(task_id, options), daemon=True)
    t.start()
    return task_id


def get_status(task_id: str) -> Dict[str, Any]:
    with _tasks_lock:
        t = _tasks.get(task_id, {})
    # attach a small log tail for UI
    try:
        out_dir = t.get('output_dir')
        if out_dir:
            log_path = os.path.join(out_dir, 'pipeline.log')
            if os.path.isfile(log_path):
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                t = dict(t)
                t['log_tail'] = ''.join(lines[-200:])
    except Exception:
        pass
    return t


def list_tasks() -> Dict[str, Any]:
    with _tasks_lock:
        return dict(_tasks)


def _run_subprocess(cmd, cwd, task_id, stage_name, progress_after=0):
    """Run subprocess, stream output to log and raise if fails."""
    _update_task(task_id, stage=stage_name, status='running')
    _write_log(task_id, f"--- START {stage_name}: {cmd}")
    try:
        # open log to capture stdout/stderr
        out_dir = os.path.join(OUTPUT_DIR, task_id)
        log_path = os.path.join(out_dir, f"{stage_name}.log")
        with open(log_path, 'wb') as logf:
            proc = subprocess.run(cmd, cwd=cwd, stdout=logf, stderr=subprocess.STDOUT, check=True)
        _write_log(task_id, f"--- END {stage_name} (success)")
        if progress_after:
            _update_task(task_id, progress=progress_after)
    except subprocess.CalledProcessError as e:
        _write_log(task_id, f"--- END {stage_name} (failed): {e}")
        _update_task(task_id, status='failed', last_message=f"Stage {stage_name} failed: {e}")
        raise


def _update_task(task_id: str, **kwargs):
    with _tasks_lock:
        t = _tasks.get(task_id)
        if not t:
            return
        t.update(kwargs)
        _persist_tasks()


def _find_latest_defect_report_in_output():
    # search for *_defect_report.json in output root
    candidates = []
    for root, dirs, files in os.walk(OUTPUT_DIR):
        for f in files:
            if f.endswith('_defect_report.json'):
                candidates.append(os.path.join(root, f))
    if not candidates:
        return None
    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return candidates[0]


def _run_pipeline_thread(task_id: str, options: Dict[str, Any]):
    python_exec = _choose_python_exec()
    cwd = PROJECT_ROOT
    try:
        # support a fast mock mode for local UI/testing without calling external services
        if options and (options.get('mock') or options.get('dry_run')):
            _update_task(task_id, status='running', stage='analysis', progress=5)
            _write_log(task_id, 'MOCK: starting analysis')
            time.sleep(0.5)
            # create a fake defect report
            out_dir = os.path.join(OUTPUT_DIR, task_id)
            os.makedirs(out_dir, exist_ok=True)
            defect_path = os.path.join(out_dir, 'sample_defect_report.json')
            try:
                with open(defect_path, 'w', encoding='utf-8') as f:
                    json.dump({
                        'project': 'mock',
                        'files': [],
                        'summary': {'total_defects': 0}
                    }, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
            _update_task(task_id, progress=20, artifacts={'defect_report': os.path.basename(defect_path)})
            _write_log(task_id, 'MOCK: analysis done')

            _update_task(task_id, stage='detection', progress=30)
            _write_log(task_id, 'MOCK: starting detection')
            time.sleep(0.5)
            _update_task(task_id, progress=60)
            _write_log(task_id, 'MOCK: detection done')

            _update_task(task_id, stage='repair', progress=65)
            _write_log(task_id, 'MOCK: starting repair')
            time.sleep(0.5)
            # create a fake repair report
            repair_path = os.path.join(out_dir, 'sample_repair_report.json')
            try:
                with open(repair_path, 'w', encoding='utf-8') as f:
                    json.dump({'repairs': [], 'success': True}, f, ensure_ascii=False)
            except Exception:
                pass
            _update_task(task_id, progress=90)
            _write_log(task_id, 'MOCK: repair done')

            _update_task(task_id, stage='quality', progress=95)
            _write_log(task_id, 'MOCK: starting quality')
            time.sleep(0.3)
            # create a fake quality html
            quality_path = os.path.join(out_dir, 'sample_quality_report.html')
            try:
                with open(quality_path, 'w', encoding='utf-8') as f:
                    f.write('<html><body><h1>Mock Quality Report</h1></body></html>')
            except Exception:
                pass

            # finalize
            with _tasks_lock:
                _tasks[task_id].setdefault('artifacts', {}).update({
                    'defect_report': os.path.basename(defect_path),
                    'repair_report': os.path.basename(repair_path),
                    'quality_report': os.path.basename(quality_path)
                })
                _tasks[task_id]['status'] = 'finished'
                _tasks[task_id]['stage'] = 'finished'
                _tasks[task_id]['progress'] = 100
                _tasks[task_id]['finished_at'] = time.time()
                _persist_tasks()
            _write_log(task_id, 'MOCK: pipeline completed')
            return
        _update_task(task_id, status='running', stage='analysis', progress=5)
        # Stage 1: run_analysis.py
        _run_subprocess([python_exec, os.path.join(PROJECT_ROOT, 'run_analysis.py')], cwd, task_id, 'analysis', progress_after=25)

        # Stage 2: run_detector.py
        _update_task(task_id, stage='detection', progress=30)
        _run_subprocess([python_exec, os.path.join(PROJECT_ROOT, 'run_detector.py')], cwd, task_id, 'detection', progress_after=65)

        # find defect report
        defect_report = _find_latest_defect_report_in_output()
        if not defect_report:
            # try to use output/default name
            raise FileNotFoundError('未找到缺陷报告')
        _update_task(task_id, artifacts={'defect_report': defect_report})

        # Stage 3: main_unified (repair & quality)
        _update_task(task_id, stage='repair', progress=70)
        _run_subprocess([python_exec, os.path.join(PROJECT_ROOT, 'main_unified.py'), '--defect-report', defect_report], cwd, task_id, 'repair', progress_after=95)

        # Optionally: quality step may be internal to main_unified; mark completion
        _update_task(task_id, stage='quality', progress=98)

        # collect artifacts (repair report json, quality html, defect report)
        artifacts = {}
        out_task_dir = os.path.join(OUTPUT_DIR, task_id)
        os.makedirs(out_task_dir, exist_ok=True)

        # helper to find candidate files and copy them into task output dir
        def _find_and_copy(patterns):
            found = []
            for root, dirs, files in os.walk(PROJECT_ROOT):
                for f in files:
                    for pat in patterns:
                        if f.endswith(pat):
                            src = os.path.join(root, f)
                            if os.path.isfile(src):
                                dst_name = f
                                dst = os.path.join(out_task_dir, dst_name)
                                try:
                                    shutil.copy2(src, dst)
                                except Exception:
                                    # best-effort copy
                                    try:
                                        with open(src, 'rb') as rs, open(dst, 'wb') as ws:
                                            ws.write(rs.read())
                                    except Exception:
                                        continue
                                found.append(dst_name)
            return found

        # patterns to collect
        repair_files = _find_and_copy(['_repair_report.json', '_repair_report_2025', '_repair_report_'])
        quality_files = _find_and_copy(['_quality_report.html', '_quality_report'])
        defect_files = _find_and_copy(['_defect_report.json'])

        # record artifacts by logical name
        if defect_files:
            artifacts['defect_report'] = defect_files[-1]
        if repair_files:
            artifacts['repair_report'] = repair_files[-1]
        if quality_files:
            artifacts['quality_report'] = quality_files[-1]

        # merge artifacts into task, mark finished
        with _tasks_lock:
            _tasks[task_id].setdefault('artifacts', {}).update(artifacts)
            _tasks[task_id]['status'] = 'finished'
            _tasks[task_id]['stage'] = 'finished'
            _tasks[task_id]['progress'] = 100
            _tasks[task_id]['finished_at'] = time.time()
            _persist_tasks()
        _write_log(task_id, 'PIPELINE COMPLETED')
    except Exception as e:
        _update_task(task_id, status='failed', last_message=str(e), stage=_tasks.get(task_id, {}).get('stage'))
        _write_log(task_id, f'PIPELINE ERROR: {e}')
        return


if __name__ == '__main__':
    # quick manual test
    tid = start_pipeline({})
    print('Started', tid)
    import time
    while True:
        s = get_status(tid)
        print(s)
        if s.get('status') in ('finished', 'failed'):
            break
        time.sleep(2)
