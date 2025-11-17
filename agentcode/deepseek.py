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
    """DeepSeek API客户端 - 支持Python/QT/C++/Java项目的类与函数结构识别"""

    def __init__(self, api_key: str = None, config_path: str = "config.json"):
        self.config_path = config_path
        self.config = self._load_config()
        deepseek_config = self.config.get("deepseek", {})
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY") or deepseek_config.get("api_key")
        self._validate_config()

     # ★新增：安全JSON解析函数
    # ===========================================================
    def _safe_json_parse(self, response_text: str) -> dict:
        """从 DeepSeek 响应中安全提取 JSON，兼容 markdown ```json``` 包裹"""
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            pass

        # 尝试提取 ```json ... ``` 块
        match = re.search(r"```json\s*(.*?)\s*```", response_text, re.S)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试提取第一个大括号包裹的JSON片段
        try:
            start = response_text.find("{")
            end = response_text.rfind("}")
            if start >= 0 and end > start:
                snippet = response_text[start:end + 1]
                return json.loads(snippet)
        except Exception:
            pass

        print("[警告] 无法从 DeepSeek 响应中提取有效 JSON。")
        return {}
    
    # 基础配置加载与验证

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

    # 网络请求接口
    def _post_request(self, content: str) -> str:
        """发送请求到DeepSeek API"""
        deepseek_config = self.config.get("deepseek", {})

        request_data = {
            "model": deepseek_config["model"],
            "messages": [
                {"role": "system", "content": "你是专业的软件代码结构分析助手，能识别Python、C、C++、QT、Java项目的类与函数结构"},
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

    # 本地文件解析（fallback）

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

    def _local_parse_java(self, file_path: str) -> Dict[str, List[str]]:
        """本地提取Java类与方法定义"""
        result = {"classes": [], "functions": []}
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                code = f.read()
            result["classes"] = re.findall(r'class\s+(\w+)', code)
            result["functions"] = re.findall(r'(?:public|private|protected)?\s+\w+\s+(\w+)\s*\(', code)
        except Exception:
            pass
        if not result["classes"]:
            result["classes"] = [f"[自动填充]{Path(file_path).stem}"]
        if not result["functions"]:
            result["functions"] = ["[自动填充]未识别方法"]
        return result
    
    # 新增C文件解析
    def _local_parse_c(self, file_path: str) -> Dict[str, List[str]]:
        """本地提取C语言函数定义"""
        result = {"classes": [], "functions": []}
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                code = f.read()
            result["functions"] = re.findall(r'\b[A-Za-z_][A-Za-z0-9_]*\s*\(', code)
        except Exception:
            pass
        if not result["functions"]:
            result["functions"] = ["[自动填充]未识别函数"]
        return result    

    # 主分析函数

    def generate_raw_analysis(self, file_data: Dict[str, Any]) -> Dict[str, Any]:
        """生成包含类和函数的raw_analysis，针对多语言优化"""
        python_files = file_data.get("python_files", [])
        qt_files = file_data.get("qt_files", [])
        java_files = file_data.get("java_files", [])
        c_files = file_data.get("c_files", [])
        cpp_files = file_data.get("cpp_files", [])
        all_files = python_files + c_files + cpp_files + java_files + qt_files

        if not all_files:
            return {"modules": {}}

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

        prompt = f"""请从以下多语言代码中提取类和函数信息：
{chr(10).join(file_contents)}

输出严格为JSON格式：
{{
  "modules": {{
    "文件名": {{
      "classes": ["类1", "类2"],
      "functions": ["函数1", "函数2"]
    }}
  }}
}}
"""

        response = self._post_request(prompt)

        # ★修改：改为使用 _safe_json_parse 而非直接 json.loads
        result = self._safe_json_parse(response)

        # ★修改：增强容错逻辑，防止误覆盖正确数据
        if not result or "modules" not in result:
            print(f"[警告] DeepSeek解析失败，使用本地解析。响应预览: {response[:400]}")
            result = {"modules": {}}
            for file in all_files:
                if file.endswith(".java"):
                    result["modules"][file] = self._local_parse_java(file)
                elif file.endswith((".c", ".cc", ".cxx")):
                    result["modules"][file] = self._local_parse_c(file)
                elif file.endswith((".cpp", ".hpp", ".h", ".ui", ".qml")):
                    result["modules"][file] = self._local_parse_cpp_ui(file)
                else:
                    result["modules"][file] = {"classes": [], "functions": []}
        else:
            # 确保每个文件都有条目
            for file in all_files:
                if file not in result["modules"]:
                    result["modules"][file] = self._local_parse_cpp_ui(file)
        return result
    
    # 项目级别分析
    def analyze_project(self, project_data: Dict[str, Any]) -> Dict[str, Any]:
        """通用项目分析方法，支持混合项目"""
        all_files = project_data["all_files"]
        if not all_files:
            return {"summary": "未检测到任何支持的项目文件"}

        qt_files = project_data.get("qt_files", [])
        c_files = project_data.get("c_files", [])
        cpp_files = project_data.get("cpp_files", [])
        java_files = project_data.get("java_files", [])
        python_files = project_data.get("python_files", [])

        # 修改
        if all([c_files, cpp_files, java_files, python_files, qt_files]):
            project_type = "混合项目（C/C++/Java/Python）"
        elif java_files:
            project_type = "Java项目"
        elif c_files and not cpp_files:
            project_type = "C项目"
        elif cpp_files:
            project_type = "C++项目"
        elif python_files:
            project_type = "Python项目"
        else:
            project_type = "其他类型项目"

        deepseek_config = self.config.get("deepseek", {})
        chunk_size = deepseek_config.get("chunk_size", 10)
        total_chunks = math.ceil(len(all_files) / chunk_size)
        chunk_results = []

        for i in range(total_chunks):
            start, end = i * chunk_size, (i + 1) * chunk_size
            chunk_files = all_files[start:end]
            chunk_prompt = self._get_project_chunk_prompt(chunk_files, i + 1, total_chunks)
            chunk_result = self._post_request(chunk_prompt)
            chunk_results.append(chunk_result)
            print(f"已完成文件分析进度: {i + 1}/{total_chunks}")

        summary_prompt = self._get_project_chunk_prompt(chunk_results, project_data, project_type)
        final_summary = self._post_request(summary_prompt)

        return {
            "total_files": len(all_files),
            "project_type": project_type,
            "analysis_chunks": total_chunks,
            "chunk_results": chunk_results,
            "summary": final_summary
        }

    # 提示生成辅助函数（修改）

    def _get_project_chunk_prompt(self, files: List[str], num: int, total: int) -> str:
        return f"""请分析以下项目文件（第{num}/{total}部分）：
{json.dumps(files, indent=2, ensure_ascii=False)}
请识别其中的语言类型（Python / Java / C / C++ / QT / 混合语言），并提取：
- 类和函数定义
- 模块间依赖关系
- 主入口逻辑
请输出结构化JSON。
"""

    def _get_project_summary_prompt(self, chunk_results: List[str], project_data: Dict[str, Any]) -> str:
        java_files = project_data.get("java_files", [])
        qt_files = project_data.get("qt_files", [])
        python_files = project_data.get("python_files", [])
        cpp_files = project_data.get("cpp_files", [])
        c_files = project_data.get("c_files", [])

        if java_files:
            project_type = "Java项目"
        elif cpp_files:
            project_type = "C++项目）"
        elif c_files:
            project_type = "C项目"
        elif qt_files:
            project_type = "QT项目"
        elif python_files:
            project_type = "Python项目"
        else:
            project_type = "混合项目"

        return f"""基于以下分块分析结果，总结{project_type}情况：
{chr(10).join([f"第{i+1}部分: {result}" for i, result in enumerate(chunk_results)])}

请总结：
1. 项目整体功能和架构设计
2. 类与模块的依赖关系
3. 主要逻辑流程（如main入口）
4. 可改进点与潜在架构优化建议
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
