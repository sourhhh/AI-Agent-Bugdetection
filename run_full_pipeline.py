import subprocess
import sys
import os
import glob
import time

# 可通过环境变量覆盖虚拟环境 Python 路径
VENV_PYTHON = os.environ.get('VENV_PYTHON', r"D:\PycharmProjects\AI Agent\backend\.venv\Scripts\python.exe")

# 选择 Python 可执行文件：优先使用指定的虚拟环境，否则回退到当前解释器
python_exec = VENV_PYTHON if (VENV_PYTHON and os.path.isfile(VENV_PYTHON)) else sys.executable
if python_exec != VENV_PYTHON:
    print(f"警告：指定的 VENV_PYTHON 不可用，回退到当前解释器：{python_exec}")

BASE_DIR = os.path.dirname(__file__)

def run_script(script_name, args=None, stage_name=None):
    args = args or []
    script_path = os.path.join(BASE_DIR, script_name)
    if not os.path.isfile(script_path):
        raise FileNotFoundError(f"找不到脚本: {script_path}")
    print(f"=> 正在运行阶段: {stage_name or script_name} ...")
    subprocess.run([python_exec, script_path] + args, check=True)
    print(f"<= 阶段完成: {stage_name or script_name}")

def find_latest_defect_report():
    out_dir = os.path.join(BASE_DIR, 'output')
    pattern = os.path.join(out_dir, '*_defect_report.json')
    files = glob.glob(pattern)
    if not files:
        # 尝试任何 json 文件
        files = glob.glob(os.path.join(out_dir, '*.json'))
        if not files:
            raise FileNotFoundError(f"未在 {out_dir} 找到缺陷报告文件")
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return files[0]

try:
    # 1) 项目分析
    run_script('run_analysis.py', stage_name='项目分析 (run_analysis)')

    # 2) 缺陷检测
    run_script('run_detector.py', stage_name='缺陷检测 (run_detector)')

    # 3) 寻找检测结果并传给修复/质量评估流程
    defect_report = find_latest_defect_report()
    print(f"检测报告位置: {defect_report}")

    # 4) 代码修复与质量评估（main_unified 支持 --defect-report 参数）
    run_script('main_unified.py', args=['--defect-report', defect_report], stage_name='修复与质量评估 (main_unified)')

    # 最终说明（更精确）
    print("✅ 全流程完成：分析 -> 检测 -> 修复 -> 代码质量评估 均已执行（请查看 output 目录和日志）。")

except subprocess.CalledProcessError as e:
    print(f"子进程在阶段执行时返回非零退出码: {e.returncode}, 命令: {e.cmd}")
    sys.exit(e.returncode)
except FileNotFoundError as e:
    print(f"执行失败，文件未找到: {e}")
    sys.exit(2)
except Exception as e:
    print(f"执行过程中出现异常: {e}")
    sys.exit(3)