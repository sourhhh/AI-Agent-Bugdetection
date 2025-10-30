import os
import sys
import importlib

import json


def check_environment():
    """检查运行环境"""
    print("🔍 检查运行环境...")

    # 检查Python版本
    print(f"Python版本: {sys.version}")

    # 检查必要的模块
    required_modules = ['requests', 'tqdm']
    missing_modules = []

    for module in required_modules:
        try:
            importlib.import_module(module)
            print(f"✅ {module} 已安装")
        except ImportError:
            print(f"❌ {module} 未安装")
            missing_modules.append(module)

    # 检查项目模块
    project_modules = [
        'agents.decision_manager',
        'agents.code_fixer',
        'schemas.defect_report',
        'schemas.repair_plan',
        'schemas.fix_result',
        'utils.file_utils',
        'utils.ai_fixer',
        'utils.ai_analyzer'
    ]

    print("\n🔧 检查项目模块...")
    for module_path in project_modules:
        try:
            importlib.import_module(module_path)
            print(f"✅ {module_path} 可导入")
        except ImportError as e:
            print(f"❌ {module_path} 导入失败: {e}")

    # 检查API密钥
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if api_key:
        print(f"✅ DEEPSEEK_API_KEY 已设置 (长度: {len(api_key)})")
    else:
        print("❌ DEEPSEEK_API_KEY 未设置，请设置环境变量")

    # 检查缺陷报告文件
    report_files = [
        "requests_cache_defect_report.json",
        "requests_cache_defect_report2.json"
    ]

    print("\n📁 检查缺陷报告文件...")
    for report_file in report_files:
        if os.path.exists(report_file):
            file_size = os.path.getsize(report_file) / 1024 / 1024
            print(f"✅ {report_file} 存在，大小: {file_size:.2f} MB")

            # 尝试读取文件内容
            try:
                with open(report_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                files_count = len(data.get('files', []))
                defects_count = sum(len(file.get('defects', [])) for file in data.get('files', []))
                print(f"   - 包含 {files_count} 个文件，{defects_count} 个缺陷")
            except Exception as e:
                print(f"   - 文件读取失败: {e}")
        else:
            print(f"❌ {report_file} 不存在")

    # 总结
    print("\n📋 环境检查总结:")
    if missing_modules:
        print(f"❌ 缺少模块: {', '.join(missing_modules)}")
        print(f"   请运行: pip install {' '.join(missing_modules)}")
    else:
        print("✅ 所有必要模块已安装")

    if not api_key:
        print("❌ 请设置 DEEPSEEK_API_KEY 环境变量")
    else:
        print("✅ API密钥已配置")

    if any(os.path.exists(f) for f in report_files):
        print("✅ 缺陷报告文件存在")
    else:
        print("❌ 没有找到缺陷报告文件")


if __name__ == "__main__":
    check_environment()