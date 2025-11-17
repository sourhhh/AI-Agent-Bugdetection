# 解决模块导入问题
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from agents.defect_detector_qt import DefectDetectorQt
from schemas.defect_report import DefectReport
from schemas.project_context import ProjectContext


def extract_files_from_raw_analysis(raw_analysis, project_root):
    """从raw_analysis中提取所有文件路径，使用 project_root 拼接相对路径"""
    file_paths = []
    if raw_analysis and "modules" in raw_analysis:
        for file_path in raw_analysis["modules"].keys():
            # 确保文件路径是绝对路径
            if not os.path.isabs(file_path):
                # 如果是相对路径，使用传入的 project_root（如果有）拼接
                if project_root:
                    file_path = os.path.join(project_root, file_path)
            file_paths.append(file_path)
    return file_paths


def test_detect_qt_project(project_path=None):
    """测试对Qt项目的缺陷检测（使用A提供的JSON输入）"""
    print("\n" + "=" * 60)
    print("🧪 开始测试Qt项目缺陷检测")
    print("=" * 60)

    start_time = time.time()

    # 1. 根据项目路径自动确定JSON文件路径
    if project_path:
        project_name = os.path.basename(project_path)
        a_json_path = f"./input_data/{project_name}_analysis.json"
    else:
        a_json_path = "./input_data/qt_project_analysis.json"  # 默认

    if not os.path.exists(a_json_path):
        print(f"❌ 未找到A的JSON文件：{a_json_path}")
        print("💡 请确保 qt_project_analysis.json 文件在 input_data 目录下")
        return

    try:
        with open(a_json_path, "r", encoding="utf-8") as f:
            a_full_data = json.load(f)
        print(f"✅ 成功读取 qt_project_analysis.json 文件")
    except Exception as e:
        print(f"❌ 读取JSON文件失败：{str(e)}")
        return

    # 2. 提取project_context字段和raw_analysis
    project_context_data = a_full_data.get("project_context")
    raw_analysis_data = a_full_data.get("raw_analysis", {})

    if not project_context_data:
        print("❌ qt_project_analysis.json 中缺少'project_context'字段")
        return

    # 3. 修复：从raw_analysis中提取实际的文件路径
    actual_files = extract_files_from_raw_analysis(raw_analysis_data, project_context_data.get("project_root", ""))

    if not actual_files:
        print("❌ 从raw_analysis中未提取到任何文件路径")
        print(f"raw_analysis keys: {list(raw_analysis_data.keys()) if raw_analysis_data else 'None'}")
        return

    # 4. 更新project_context_data中的python_files
    project_context_data["python_files"] = actual_files

    # 5. 创建ProjectContext对象
    try:
        project_context = ProjectContext(**project_context_data)
        print(f"✅ 成功解析Qt项目输入")
        print(f"📁 项目根路径: {project_context.project_root}")
        print(f"📄 待检测文件总数: {len(project_context.python_files)}")
        print(f"🔧 C++文件数: {len(project_context.cpp_files)}")

        # 显示文件类型统计
        file_types = {}
        for file_path in project_context.python_files:
            ext = os.path.splitext(file_path)[1].lower()
            file_types[ext] = file_types.get(ext, 0) + 1

        print(f"📊 文件类型统计: {file_types}")

        # 显示前10个文件示例
        print(f"📄 文件示例（前10个）:")
        for i, file_path in enumerate(project_context.python_files[:10]):
            print(f"  {i + 1}. {os.path.basename(file_path)}")

        if len(project_context.python_files) > 10:
            print(f"  ... 还有 {len(project_context.python_files) - 10} 个文件")

    except Exception as e:
        print(f"❌ 创建ProjectContext失败：{str(e)}")
        return

    # 6. 验证本地文件路径
    sample_files = project_context.cpp_files[:5] if len(project_context.cpp_files) >= 5 else project_context.cpp_files
    existing_files = []
    missing_files = []

    for file_path in sample_files:
        if os.path.exists(file_path):
            existing_files.append(file_path)
        else:
            missing_files.append(file_path)

    print(f"\n🔍 文件路径验证:")
    print(f"  ✅ 存在的文件: {len(existing_files)}个")
    print(f"  ❌ 缺失的文件: {len(missing_files)}个")

    if missing_files:
        print(f"⚠️  警告：以下文件在本地不存在：")
        for missing_file in missing_files[:3]:  # 只显示前3个
            print(f"    - {missing_file}")
        if len(missing_files) > 3:
            print(f"    ... 还有 {len(missing_files) - 3} 个文件")
        print("💡 提示：缺失的文件将跳过检测")

    if not project_context.cpp_files:
        print("❌ 没有找到C++文件进行检测")
        return

    print(f"\n⏳ 开始检测 {len(project_context.cpp_files)} 个C++/Qt文件...")
    print("💡 预计需要几分钟时间，请耐心等待...")

    # 7. 调用DefectDetectorQt进行检测
    detector = DefectDetectorQt()

    # 将ProjectContext转换为JSON字符串传递给detector
    project_context_json = project_context.to_json()

    print("🚀 启动缺陷检测引擎...")
    defect_report_json = detector.detect(project_context_json)

    # 8. 解析并展示检测结果
    defect_report = DefectReport.from_json(defect_report_json)
    print("\n" + "=" * 60)
    print("📊 Qt项目缺陷检测结果汇总")
    print("=" * 60)

    print(f"📁 检测文件数：{len(defect_report.files)}")
    total_defects = sum(len(fd.defects) for fd in defect_report.files)
    print(f"🐛 总缺陷数：{total_defects}")

    if total_defects == 0:
        print("🎉 未发现任何缺陷")
        # 计算总耗时
        end_time = time.time()
        elapsed_time = end_time - start_time
        minutes = int(elapsed_time // 60)
        seconds = int(elapsed_time % 60)
        print(f"⏱️  总检测时间：{minutes}分{seconds}秒")
        return

    # 统计各类缺陷
    cpp_specific_defects = {
        "memory": 0, "concurrency": 0, "qt_specific": 0,
        "performance": 0, "security": 0, "syntax": 0, "logic": 0, "code_smell": 0
    }
    llm_defects_count = 0
    tool_breakdown = {"cppcheck": 0, "llm": 0, "detector": 0}

    for file_defects in defect_report.files:
        for defect in file_defects.defects:
            if defect.type in cpp_specific_defects:
                cpp_specific_defects[defect.type] += 1
            if defect.tool == "llm":
                llm_defects_count += 1
            if defect.tool in tool_breakdown:
                tool_breakdown[defect.tool] += 1

    print(f"\n🔧 工具检测统计：")
    for tool, count in tool_breakdown.items():
        if count > 0:
            print(f"  {tool}: {count}个缺陷")

    print(f"\n📋 缺陷类型统计：")
    for defect_type, count in cpp_specific_defects.items():
        if count > 0:
            print(f"  {defect_type}: {count}个缺陷")

    print(f"\n🤖 LLM检测到的缺陷数：{llm_defects_count}")
    print(f"📈 按严重程度统计：{defect_report.summary}")

    # 9. 保存缺陷报告
    output_dir = "./output"
    os.makedirs(output_dir, exist_ok=True)

    # 根据项目路径自动生成输出文件名
    project_name = os.path.basename(project_path) if project_path else "qt_project"
    output_path = os.path.join(output_dir, f"{project_name}_defect_report.json")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(defect_report_json)

    # 计算并显示总耗时
    end_time = time.time()
    elapsed_time = end_time - start_time
    minutes = int(elapsed_time // 60)
    seconds = int(elapsed_time % 60)
    print(f"\n✅ Qt项目缺陷报告已保存到：{output_path}")
    print(f"⏱️  总检测时间：{minutes}分{seconds}秒")

    # 10. 验证输出格式
    required_fields = ["files", "summary"]
    report_data = json.loads(defect_report_json)
    for field in required_fields:
        if field not in report_data:
            raise ValueError(f"❌ 缺陷报告缺少必填字段：{field}，不符合接口规范")
    print("✅ 缺陷报告格式符合接口规范，可以传给C角色")

    # 显示前10个缺陷示例
    print(f"\n🔍 缺陷示例（前10个）：")
    # 第一步：汇总所有缺陷到一个列表
    all_defects = []
    for file_defects in defect_report.files:
        file_name = os.path.basename(file_defects.file_path)
        for defect in file_defects.defects:
            # 保存缺陷及对应的文件名（用于展示）
            all_defects.append((defect, file_name))

    # 第二步：筛选多元化的缺陷（优先不同类型）
    selected_defects = []
    selected_types = set()  # 记录已选中的缺陷类型

    # 第一遍：优先选择未出现过的类型
    for defect, file_name in all_defects:
        if len(selected_defects) >= 10:
            break
        if defect.type not in selected_types:
            selected_defects.append((defect, file_name))
            selected_types.add(defect.type)

    # 第二遍：如果还没选满10个，补充其他类型（允许重复类型）
    if len(selected_defects) < 10:
        for defect, file_name in all_defects:
            if len(selected_defects) >= 10:
                break
            # 检查该缺陷是否已被选中（避免重复）
            is_duplicate = any(
                d.type == defect.type and d.line_number == defect.line_number and d.message == defect.message
                for d, _ in selected_defects
            )
            if not is_duplicate:
                selected_defects.append((defect, file_name))

    # 第三步：展示筛选后的结果
    for i, (defect, file_name) in enumerate(selected_defects[:10]):
        severity_icon = {
            "CRITICAL": "🔴",
            "HIGH": "🟠",
            "MEDIUM": "🟡",
            "LOW": "🔵"
        }.get(defect.severity, "⚪")

        print(f"  {i + 1}. {severity_icon} {file_name}:{defect.line_number}")
        print(f"    类型: {defect.type}, 工具: {defect.tool}")
        print(f"    描述: {defect.message}")
        print()

    # 检查LLM是否有输出
    if llm_defects_count == 0:
        print("⚠️  警告：LLM未检测到任何缺陷，可能LLM服务不可用或文件内容为空")
    else:
        print(f"✅ LLM成功检测到 {llm_defects_count} 个缺陷")

    # 添加检测总结
    print(f"\n📋 检测总结:")
    print(f"  ✅ 总文件数: {len(project_context.python_files)}")
    print(f"  ✅ C++相关文件: {len(project_context.cpp_files)}")
    print(f"  ✅ 实际检测文件: {len(defect_report.files)}")
    print(f"  ✅ 发现缺陷: {total_defects} 个")
    print(f"  ✅ LLM检测: {llm_defects_count} 个缺陷")


if __name__ == "__main__":
    # 测试Qt项目
    test_detect_qt_project()