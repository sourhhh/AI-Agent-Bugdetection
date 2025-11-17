import json
import os

from agentcode.analyzer import ProjectAnalyst
from agentcode.schemas.project_context import ProjectContext


if __name__ == "__main__":
    # 指定项目路径
    #project_path = "D:\\PY\\QtWork"
    #project_path = "D:\\PY\\requests-cache-main"
    #project_path = "D:\\PY\\SWE-bench"
    #project_path = "D:\\PY\\MSR_20_Code_vulnerability_CSV_Dataset"     #BigVul数据集
    #project_path = "D:\\PY\\devign"  # Devign数据集
    project_path = "D:\\PY\\defects4j"
    #project_path = "D:\\PY\\BugsInPy"  # BugsInPy数据集
    


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

    # 确保input_data文件夹存在，不存在则创建
    os.makedirs("input_data", exist_ok=True)
    # 修改保存路径和文件名
    #json_path = "input_data/QtWork_analysis.json"
    #json_path = "input_data/requests_cache_analysis.json"
    #json_path = "input_data/SWE-bench_analysis.json"
    json_path = "input_data/defects4j_analysis.json"
    #json_path = "input_data/MSR_20_Code_vulnerability_CSV_Dataset_analysis.json"
    #json_path = "input_data/devign_analysis.json"
    #json_path = "input_data/BugsInPy_analysis.json"


    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(compatible_result, f, indent=4, ensure_ascii=False)
    print(f"分析结果已保存（标准接口格式）：{json_path}")
