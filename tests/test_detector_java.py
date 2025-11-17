# 解决模块导入问题
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from agents.defect_detector_java import DefectDetectorJava
from schemas.defect_report import DefectReport
from schemas.project_context import ProjectContext


def normalize_paths(project_context: ProjectContext) -> None:
    corrected_files = []
    for file_path in project_context.python_files:
        if not os.path.isabs(file_path):
            absolute_path = os.path.join(project_context.project_root, file_path)
            corrected_files.append(os.path.normpath(absolute_path))
        else:
            corrected_files.append(os.path.normpath(file_path))
    project_context.python_files = corrected_files

    # 也处理 java_files（一些分析器输出可能只包含相对路径）
    corrected_java = []
    for file_path in getattr(project_context, 'java_files', []):
        if not file_path:
            continue
        if not os.path.isabs(file_path):
            absolute_path = os.path.join(project_context.project_root, file_path)
            corrected_java.append(os.path.normpath(absolute_path))
        else:
            corrected_java.append(os.path.normpath(file_path))
    if hasattr(project_context, 'java_files'):
        project_context.java_files = corrected_java


def summarize_file_types(file_paths):
    statistics = {}
    for file_path in file_paths:
        ext = os.path.splitext(file_path)[1].lower()
        statistics[ext] = statistics.get(ext, 0) + 1
    return statistics


def test_detect_java_project(project_path=None):
    """测试对Java项目的缺陷检测（使用A提供的JSON输入）"""
    print("\n" + "=" * 60)
    print("🧪 开始测试Java项目缺陷检测")
    print("=" * 60)

    start_time = time.time()
    # 1. 根据项目路径自动确定JSON文件路径
    if project_path:
        project_name = os.path.basename(project_path)
        a_json_path = f"./input_data/{project_name}_analysis.json"
    else:
        a_json_path = "./input_data/defects4j_analysis.json"

    if not os.path.exists(a_json_path):
        print(f"❌ 未找到A的JSON文件：{a_json_path}")
        print("💡 请确认 defects4j_analysis.json 是否位于 input_data 目录")
        return

    try:
        with open(a_json_path, "r", encoding="utf-8") as f:
            a_full_data = json.load(f)
        print(f"✅ 成功读取 {os.path.basename(a_json_path)} 文件")
    except Exception as e:
        print(f"❌ 读取JSON文件失败：{str(e)}")
        return

    project_context_data = a_full_data.get("project_context")
    if not project_context_data:
        print("❌ JSON 中缺少 'project_context' 字段")
        return

    try:
        if isinstance(project_context_data, dict):
            project_context = ProjectContext.from_json(json.dumps(project_context_data))
        else:
            project_context = ProjectContext.from_json(project_context_data)
    except Exception as e:
        print(f"❌ 解析ProjectContext失败：{str(e)}")
        return

    # 如果project_context中没有java_files，尝试从 raw_analysis.modules 中提取（向后兼容）
    if not getattr(project_context, 'java_files', []):
        raw_modules = a_full_data.get('raw_analysis', {}).get('modules', {})
        inferred_java = [fp for fp in raw_modules.keys() if fp.lower().endswith('.java')]
        if inferred_java:
            project_context.java_files = inferred_java

    normalize_paths(project_context)

    java_files = project_context.java_files
    print(f"📁 项目根路径: {project_context.project_root}")
    print(f"📄 待检测文件总数: {len(project_context.python_files)}")
    print(f"🧩 Java文件数: {len(java_files)}")

    if len(java_files) == 0:
        print("⚠️ 未找到任何Java文件，无法继续检测")
        return

    file_type_stats = summarize_file_types(project_context.python_files)
    print(f"📊 文件类型统计: {file_type_stats}")

    sample_files = java_files[:5] if len(java_files) >= 5 else java_files
    existing_files = []
    missing_files = []
    for file_path in sample_files:
        if os.path.exists(file_path):
            existing_files.append(file_path)
        else:
            missing_files.append(file_path)

    print("\n🔍 文件路径验证:")
    print(f"  ✅ 存在的Java文件: {len(existing_files)}个")
    print(f"  ❌ 缺失的Java文件: {len(missing_files)}个")

    if missing_files:
        for missing_file in missing_files[:3]:
            print(f"    - {missing_file}")
        if len(missing_files) > 3:
            print(f"    ... 还有 {len(missing_files) - 3} 个文件缺失")
        print("💡 缺失的文件在检测时将被跳过")

    if not existing_files:
        print("❌ 抽样文件均不存在，请检查项目路径配置")
        return

    print(f"\n⏳ 开始检测 {len(java_files)} 个Java文件...")
    print("💡 预计需要几分钟时间，请耐心等待...")

    detector = DefectDetectorJava()
    defect_report_json = detector.detect(project_context.to_json())

    defect_report = DefectReport.from_json(defect_report_json)
    print("\n" + "=" * 60)
    print("📊 Java项目缺陷检测结果汇总")
    print("=" * 60)
    print(f"📁 检测文件数：{len(defect_report.files)}")
    total_defects = sum(len(fd.defects) for fd in defect_report.files)
    print(f"🐛 总缺陷数：{total_defects}")

    if total_defects == 0:
        print("🎉 未发现任何缺陷")
    else:
        tool_breakdown = {"pmd": 0, "checkstyle": 0, "llm": 0, "detector": 0}
        type_breakdown = {"syntax": 0, "security": 0, "logic": 0, "code_smell": 0, "performance": 0, "concurrency": 0}

        for file_defects in defect_report.files:
            for defect in file_defects.defects:
                if defect.tool in tool_breakdown:
                    tool_breakdown[defect.tool] += 1
                if defect.type in type_breakdown:
                    type_breakdown[defect.type] += 1

        print("\n🔧 工具检测统计：")
        for tool, count in tool_breakdown.items():
            if count > 0:
                print(f"  {tool}: {count}个缺陷")

        print("\n📋 缺陷类型统计：")
        for defect_type, count in type_breakdown.items():
            if count > 0:
                print(f"  {defect_type}: {count}个缺陷")

    print(f"\n📈 按严重程度统计：{defect_report.summary}")

    output_dir = "./output"
    os.makedirs(output_dir, exist_ok=True)
    project_name = os.path.basename(project_path) if project_path else "defects4j"
    output_path = os.path.join(output_dir, f"{project_name}_defect_report.json")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(defect_report_json)

    end_time = time.time()
    elapsed_time = end_time - start_time
    minutes = int(elapsed_time // 60)
    seconds = int(elapsed_time % 60)
    print(f"\n✅ 缺陷报告已保存到：{output_path}")
    print(f"⏱️  总检测时间：{minutes}分{seconds}秒")

    required_fields = ["files", "summary"]
    report_data = json.loads(defect_report_json)
    for field in required_fields:
        if field not in report_data:
            raise ValueError(f"❌ 缺陷报告缺少必填字段：{field}")
    print("✅ 缺陷报告格式符合接口规范，可以传给C角色")


if __name__ == "__main__":
    test_detect_java_project()
