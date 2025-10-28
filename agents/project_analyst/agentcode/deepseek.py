# -*- coding: utf-8 -*-
import os
import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Any
import requests


class DeepSeekClient:
    """DeepSeek API客户端 - 支持QT/C++项目的类与函数结构识别"""

    def __init__(self, api_key: str = None, config_path: str = "config.json"):
        self.config_path = config_path
        self.config = self._load_config()
        deepseek_config = self.config.get("deepseek", {})
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY") or deepseek_config.get("api_key")
        self._validate_config()

    # ============================================================
    # 基础配置加载与验证
    # ============================================================

    def _load_config(self) -> Dict[str, Any]:
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"配置文件 {self.config_path} 不存在")
        except json.JSONDecodeError:
            raise ValueError(f"配置文件 {self.config_path} 格式错误")

    def _validate_config(self) -> None:
        if not self.api_key:
            raise ValueError("未找到DeepSeek API Key，请设置环境变量DEEPSEEK_API_KEY或在配置文件中配置")

        deepseek_config = self.config.get("deepseek", {})
        for key in ["api_base", "model", "timeout", "chunk_size"]:
            if key not in deepseek_config:
                raise ValueError(f"DeepSeek配置缺失必要项: {key}")

    # ============================================================
    # 网络请求接口
    # ============================================================

    def _post_request(self, content: str) -> str:
        """发送请求到DeepSeek API"""
        deepseek_config = self.config.get("deepseek", {})

        request_data = {
            "model": deepseek_config["model"],
            "messages": [
                {"role": "system", "content": "你是专业的C++/QT代码结构分析助手，准确识别类与函数定义"},
                {"role": "user", "content": content}
            ],
            "temperature": 0.7,
            "max_tokens": 4000
        }

        try:
            response = requests.post(
                f"{deepseek_config['api_base']}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json=request_data,
                timeout=deepseek_config["timeout"]
            )
            response.raise_for_status()
            result = response.json()
            if "choices" in result and result["choices"]:
                return result["choices"][0]["message"].get("content", "")
            return "API返回格式异常"
        except requests.exceptions.Timeout:
            return "API请求超时"
        except requests.exceptions.RequestException as e:
            return f"API调用失败: {e}"

    # ============================================================
    # 本地QT/C++文件解析（fallback）
    # ============================================================

    def _local_parse_cpp_ui(self, file_path: str) -> Dict[str, List[str]]:
        """本地提取C++或UI文件的类与函数信息"""
        result = {"classes": [], "functions": []}
        path = Path(file_path)
        suffix = path.suffix.lower()

        try:
            if suffix in (".h", ".hpp", ".cpp"):
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                # 提取类名
                result["classes"] = re.findall(r'class\s+(\w+)', content)
                # 提取成员函数与全局函数
                func_matches = re.findall(r'\b(\w+)::(\w+)\s*\(', content)
                if func_matches:
                    result["functions"] = [f"{c}::{m}" for c, m in func_matches]
                else:
                    result["functions"] = re.findall(r'\b(\w+)\s*\(', content)

            elif suffix == ".ui":
                tree = ET.parse(file_path)
                root = tree.getroot()
                cls = root.find("class")
                result["classes"] = [cls.text] if cls is not None else []
                # 提取控件名
                widgets = [w.attrib.get("name", "") for w in root.iter("widget") if "name" in w.attrib]
                result["functions"] = [w for w in widgets if w]
        except Exception:
            pass

        if not result["classes"]:
            result["classes"] = [f"[自动填充]{path.stem}"]
        if not result["functions"]:
            result["functions"] = ["[自动填充]未识别函数"]
        return result

    # ============================================================
    # 主分析函数
    # ============================================================

    def generate_raw_analysis(self, file_data: Dict[str, Any]) -> Dict[str, Any]:
        """生成包含类和函数的raw_analysis，针对Python和QT文件优化"""
        python_files = file_data.get("python_files", [])
        qt_files = file_data.get("qt_files", [])
        all_files = python_files + qt_files

        if not all_files:
            return {"modules": {}}

        # 读取文件内容
        file_contents = []
        for file in all_files:
            if not os.path.exists(file):
                continue
            try:
                with open(file, 'r', encoding='utf-8', errors='ignore') as f:
                    code = f.read()
                    file_contents.append(f"文件名: {file}\n内容:\n{code[:2000]}")
            except Exception as e:
                file_contents.append(f"文件名: {file}\n内容: [无法读取 - {e}]")

        # 构建提示词
        prompt = f"""# QT/C++ 代码结构提取任务
请从以下代码中提取类和函数信息。

输出严格为JSON格式：
{{
  "modules": {{
    "文件名": {{
      "classes": ["类1", "类2"],
      "functions": ["函数1", "函数2"]
    }}
  }}
}}

以下是文件内容（部分截断）：
{chr(10).join(file_contents)}
"""

        # 调用API
        response = self._post_request(prompt)

        # 尝试解析返回
        try:
            result = json.loads(response)
            if "modules" not in result:
                raise ValueError("返回中缺少'modules'字段")
            # 确保每个文件都有条目
            for file in all_files:
                if file not in result["modules"]:
                    result["modules"][file] = self._local_parse_cpp_ui(file)
            return result
        except Exception as e:
            print(f"[警告] DeepSeek解析失败: {e}")
            print(f"[响应预览]: {response[:500]}")

        # 如果解析失败则使用本地解析
        fallback = {"modules": {}}
        for file in all_files:
            fallback["modules"][file] = self._local_parse_cpp_ui(file)
        return fallback

    # ============================================================
    # 项目级别分析
    # ============================================================

    def analyze_project(self, project_data: Dict[str, Any]) -> Dict[str, Any]:
        """通用项目分析方法，支持Python和QT项目"""
        all_files = project_data["all_files"]
        if not all_files:
            return {"summary": "未检测到任何支持的项目文件"}

        qt_files = project_data.get("qt_files", [])
        python_files = project_data.get("python_files", [])

        project_type = "混合项目（Python + QT）"
        if not qt_files:
            project_type = "Python项目"
        elif not python_files:
            project_type = "QT项目（C++/QML）"

        deepseek_config = self.config.get("deepseek", {})
        chunk_size = deepseek_config.get("chunk_size", 10)
        total_chunks = math.ceil(len(all_files) / chunk_size)
        chunk_results = []

        for i in range(total_chunks):
            start, end = i * chunk_size, (i + 1) * chunk_size
            chunk_files = all_files[start:end]
            chunk_prompt = self._get_qt_chunk_prompt(chunk_files, i + 1, total_chunks)
            chunk_result = self._post_request(chunk_prompt)
            chunk_results.append(chunk_result)
            print(f"已完成文件分析进度: {i + 1}/{total_chunks}")

        summary_prompt = self._get_qt_summary_prompt(chunk_results, project_data)
        final_summary = self._post_request(summary_prompt)

        return {
            "total_files": len(all_files),
            "project_type": project_type,
            "analysis_chunks": total_chunks,
            "chunk_results": chunk_results,
            "summary": final_summary
        }

    # ============================================================
    # 提示生成辅助函数
    # ============================================================

    def _get_qt_chunk_prompt(self, files: List[str], chunk_num: int, total_chunks: int) -> str:
        return f"""请分析以下QT项目文件（第{chunk_num}/{total_chunks}部分）：
{json.dumps(files, indent=2, ensure_ascii=False)}

请从QT开发角度分析：
1. .ui文件与.cpp/.h文件的对应关系
2. .qrc资源文件的使用方式
3. QML与C++交互方式（如存在）
4. 程序启动流程和模块划分
提供结构化分析："""

    def _get_qt_summary_prompt(self, chunk_results: List[str], project_data: Dict[str, Any]) -> str:
        return f"""基于以下分块分析结果，总结QT项目情况：

分块分析结果：
{chr(10).join([f"第{i+1}部分: {result}" for i, result in enumerate(chunk_results)])}

请总结：
1. 项目整体功能和技术栈
2. UI界面与逻辑的对应关系
3. 模块间的交互方式
4. 架构设计与优化建议
"""

    def simple_chat(self, message: str) -> str:
        return self._post_request(message)

    def get_usage_info(self) -> Dict[str, Any]:
        """返回API使用配置"""
        cfg = self.config.get("deepseek", {})
        return {
            "api_base": cfg.get("api_base"),
            "model": cfg.get("model"),
            "timeout": cfg.get("timeout"),
            "chunk_size": cfg.get("chunk_size")
        }
