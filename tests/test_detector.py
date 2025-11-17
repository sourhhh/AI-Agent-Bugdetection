# 解决模块导入问题
import os
import sys
import time  # 新增计时功能

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 仅保留必要的导入
import json
from agents.defect_detector import DefectDetector
from schemas.defect_report import DefectReport
from schemas.project_context import ProjectContext


def test_detect_requests_cache(project_path=None):
    """测试对requests-cache项目的缺陷检测（使用A提供的JSON输入）"""
    # 记录开始时间
    start_time = time.time()

    # 1. 根据项目路径自动确定JSON文件路径
    if project_path:
        project_name = os.path.basename(project_path)
        a_json_path = f"./input_data/{project_name}_analysis.json"
    else:
        a_json_path = "./input_data/SWE-bench_analysis.json"  # 默认



    if not os.path.exists(a_json_path):
        raise FileNotFoundError(f"❌ 未找到A的JSON文件，请检查路径：{a_json_path}")

    with open(a_json_path, "r", encoding="utf-8") as f:
        a_full_data = json.load(f)

    # 2. 提取project_context字段
    a_project_context_str = a_full_data.get("project_context")
    if not a_project_context_str:
        raise ValueError("❌ A的JSON中缺少'project_context'字段，无法作为输入")

    # 3. 验证格式并解析
    try:
        # 兼容处理：如果已经是字典，先转换为JSON字符串
        if isinstance(a_project_context_str, dict):
            project_context = ProjectContext.from_json(json.dumps(a_project_context_str))
        else:
            project_context = ProjectContext.from_json(a_project_context_str)

        # 🔧 修复：将所有相对路径转换为绝对路径
        corrected_files = []
        for file_path in project_context.python_files:
            if not os.path.isabs(file_path):
                # 如果是相对路径，基于项目根目录转换为绝对路径
                absolute_path = os.path.join(project_context.project_root, file_path)
                corrected_files.append(absolute_path)
            else:
                corrected_files.append(file_path)

        project_context.python_files = corrected_files

        print(
            f"✅ 成功解析A的输入：项目根路径={project_context.project_root}，待检测文件数={len(project_context.python_files)}")
    except Exception as e:
        raise ValueError(f"❌ A的输入格式错误：{str(e)}")

    # 4. 验证本地文件路径 - 添加详细调试
    print(f"🔍 详细路径调试信息:")
    print(f"   项目根路径: '{project_context.project_root}'")
    print(f"   根路径是否存在: {os.path.exists(project_context.project_root)}")

    # 检查根路径下的实际文件
    if os.path.exists(project_context.project_root):
        print(f"   根路径下实际文件:")
        root_files = os.listdir(project_context.project_root)
        for file in root_files[:10]:  # 显示前10个文件
            print(f"     - {file}")
        if len(root_files) > 10:
            print(f"     ... 还有 {len(root_files) - 10} 个文件")

    # 先定义 sample_files
    sample_files = project_context.python_files[:5] if len(
        project_context.python_files) >= 5 else project_context.python_files

    print(f"   抽样检查的文件:")
    for i, file_path in enumerate(sample_files):
        print(f"     {i + 1}. '{file_path}'")
        print(f"       是否存在: {os.path.exists(file_path)}")

        # 尝试构建实际路径
        filename = os.path.basename(file_path)
        possible_path = os.path.join(project_context.project_root, filename)
        print(f"       可能路径: '{possible_path}'")
        print(f"       可能路径是否存在: {os.path.exists(possible_path)}")

    # 继续原有的宽松验证...
    existing_files = []
    missing_files = []

    for file_path in sample_files:
        if os.path.exists(file_path):
            existing_files.append(file_path)
        else:
            missing_files.append(file_path)

    print(f"  ✅ 存在的文件: {len(existing_files)}个")
    print(f"  ❌ 缺失的文件: {len(missing_files)}个")

    # 如果所有文件都缺失，让我们检查一下实际的项目结构
    if not existing_files and os.path.exists(project_context.project_root):
        print(f"🔍 尝试查找实际项目文件:")
        actual_files = []
        for root, dirs, files in os.walk(project_context.project_root):
            for file in files:
                if file.endswith('.py'):
                    full_path = os.path.join(root, file)
                    actual_files.append(full_path)

        print(f"   实际找到的Python文件: {len(actual_files)}个")
        if actual_files:
            print(f"   前5个实际文件:")
            for file in actual_files[:5]:
                print(f"     - {file}")

    # 如果有文件存在就继续，而不是全部都要存在
    if not existing_files:
        raise FileNotFoundError("❌ 所有抽样文件都不存在，请确认项目路径正确")

    print(f"✅ 文件路径验证通过，将检测 {len(existing_files)} 个存在的文件")
    print(f"⏳ 开始检测 {len(project_context.python_files)} 个文件...（预计需要一段时间）")

    # 5. 调用DefectDetector进行检测
    detector = DefectDetector()

    # 🔧 修复：直接使用修正后的project_context对象
    defect_report_json = detector.detect(project_context.to_json())

    # 6. 解析并展示检测结果，特别关注LLM结果
    defect_report = DefectReport.from_json(defect_report_json)
    print("\n📊 python项目缺陷检测结果汇总：")
    print(f"检测文件数：{len(defect_report.files)}")
    total_defects = sum(len(fd.defects) for fd in defect_report.files)
    print(f"总缺陷数：{total_defects}")

    # 统计LLM检测到的缺陷数量
    llm_defects_count = 0
    for file_defects in defect_report.files:
        for defect in file_defects.defects:
            if defect.tool == "llm":
                llm_defects_count += 1
    print(f"LLM检测到的缺陷数：{llm_defects_count}")
    print(f"按严重程度统计：{defect_report.summary}")

    # 7. 保存缺陷报告
    output_dir = "./output"
    os.makedirs(output_dir, exist_ok=True)

    # 根据项目路径自动生成输出文件名
    project_name = os.path.basename(project_path) if project_path else "SWE-bench"
    output_path = os.path.join(output_dir, f"{project_name}_defect_report.json")
    #output_path = os.path.join(output_dir, "MSR_20_Code_vulnerability_CSV_Dataset_defect_report.json")
    #output_path = os.path.join(output_dir, "devign_defect_report.json")


    with open(output_path, "w", encoding="utf-8") as f:
        f.write(defect_report_json)

    # 计算并显示总耗时
    end_time = time.time()
    elapsed_time = end_time - start_time
    minutes = int(elapsed_time // 60)
    seconds = int(elapsed_time % 60)
    print(f"\n✅ 缺陷报告已保存到：{output_path}")
    print(f"⏱️  总检测时间：{minutes}分{seconds}秒")

    # 8. 验证输出格式
    required_fields = ["files", "summary"]
    report_data = json.loads(defect_report_json)
    for field in required_fields:
        if field not in report_data:
            raise ValueError(f"❌ 缺陷报告缺少必填字段：{field}，不符合接口规范")
    print("✅ 缺陷报告格式符合接口规范，可以传给C角色")

    # 检查LLM是否有输出
    if llm_defects_count == 0:
        print("⚠️  警告：LLM未检测到任何缺陷，可能存在问题")


if __name__ == "__main__":
    # 测试Python项目
    test_detect_requests_cache()