import json
from agentcode.analyzer import ProjectAnalyst
from agentcode.schemas.project_context import ProjectContext


if __name__ == "__main__":
    # 指定 QT 项目路径
    project_path = "D:\\QtWork"
    
    # 初始化分析器（use_deepseek=True 启用 AI 分析）
    analyst = ProjectAnalyst(
        project_path=project_path,
        use_deepseek=True
    )

    analysis_result = analyst.analyze()

    project_context_raw = analysis_result.get("project_context")
    if isinstance(project_context_raw, str):
        project_context = ProjectContext.from_json(project_context_raw)
        project_context_json = json.loads(project_context_raw)
    elif isinstance(project_context_raw, dict):
        project_context = ProjectContext(**project_context_raw)
        project_context_json = json.loads(project_context.to_json())
    else:
        raise TypeError("Invalid project_context format")

    # 保留三个核心字段
    compatible_result = {
        "project_context": project_context_json,
        "raw_analysis": analysis_result.get("raw_analysis", {}),
        "deepseek_analysis": analysis_result.get("deepseek_analysis", {})
    }

    json_path = "requests_analysis_qt.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(compatible_result, f, indent=4, ensure_ascii=False)
    print(f"分析结果已保存（标准接口格式）：{json_path}")

    txt_path = "requests_analysis_qt.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("====== QT 项目分析报告 ======\n\n")

        # --- 项目信息 ---
        f.write("【ProjectContext】\n")
        f.write(json.dumps(compatible_result["project_context"], indent=4, ensure_ascii=False))
        f.write("\n\n")

        # --- 文件结构分析 ---
        f.write("【Raw Analysis - 文件结构】\n")
        modules = compatible_result.get("raw_analysis", {}).get("modules", {})
        if not modules:
            f.write("（未检测到任何可识别文件结构）\n\n")
        else:
            for file, data in modules.items():
                f.write(f"文件: {file}\n")
                f.write(f"  类: {', '.join(data.get('classes', []))}\n")
                f.write(f"  函数: {', '.join(data.get('functions', []))}\n\n")

        # --- DeepSeek 综合分析 ---
        f.write("【DeepSeek Analysis - 综合分析】\n")
        deepseek_result = compatible_result.get("deepseek_analysis", {})
        summary = deepseek_result.get("summary", "")
        if isinstance(summary, str):
            f.write(summary.strip() + "\n")
        else:
            f.write(json.dumps(summary, indent=4, ensure_ascii=False) + "\n")

    print(f"可读文本报告已保存：{txt_path}")
