"""
API客户端 - 处理所有HTTP请求和响应
"""
import requests
import json
import logging
from typing import Dict, Any, List, Tuple, Optional

logger = logging.getLogger(__name__)

# 修改这里的导入，使用相对导入
try:
    from .config import Config
except ImportError:
    # 如果相对导入失败，尝试绝对导入
    try:
        from services.config import Config
    except ImportError:
        # 如果还是失败，使用默认配置
        class Config:
            BACKEND_URL = "http://localhost:5000"
            API_TIMEOUT = 600  # 增加超时时间以适应大型文件夹处理
            APP_NAME = "CodeFixer"
            APP_VERSION = "1.0"


class APIClient:
    """API客户端类"""

    def __init__(self, base_url: str = None):
        self.base_url = base_url or Config.BACKEND_URL
        self.timeout = getattr(Config, 'API_TIMEOUT', 600)  # 增加超时时间
        self.session = requests.Session()
        self.max_batch_size = 10  # 批处理文件大小限制
        self.max_file_size_mb = 10  # 单个文件最大大小

        # 配置会话
        self.session.headers.update({
            'Content-Type': 'application/json; charset=utf-8',
            'User-Agent': 'CodeFixer-Frontend/1.0'
        })

    def _check_file_size(self, content: str) -> bool:
        """检查文件大小是否在限制范围内"""
        # 估算内容大小（粗略计算）
        size_in_mb = (len(content) * 2) / (1024 * 1024)  # 假设平均每个字符2字节
        return size_in_mb <= self.max_file_size_mb
    
    def _prepare_files_data(self, files: List[Tuple[str, str]]) -> List[Dict]:
        """准备文件数据，过滤超大文件"""
        files_data = []
        for file_name, content in files:
            # 检查文件大小
            if not self._check_file_size(content):
                logger.warning(f"文件 {file_name} 超过大小限制，已跳过")
                continue
            
            files_data.append({
                "file_name": file_name,
                "content": content
            })
        return files_data
    
    def _batch_process(self, endpoint: str, data_key: str, items: List, max_batch_size: Optional[int] = None):
        """通用批处理函数"""
        if max_batch_size is None:
            max_batch_size = self.max_batch_size
        
        all_results = {"success": True, "data": []}
        
        # 对于小批量数据直接处理
        if len(items) <= max_batch_size:
            return self._request('POST', endpoint, json={data_key: items})
        
        # 分批处理
        for i in range(0, len(items), max_batch_size):
            batch = items[i:i+max_batch_size]
            batch_result = self._request('POST', endpoint, json={data_key: batch})
            
            if not batch_result.get("success"):
                all_results["success"] = False
                all_results["error"] = batch_result.get("error", "批处理失败")
                break
            
            # 合并结果
            if "data" in batch_result and isinstance(batch_result["data"], list):
                all_results["data"].extend(batch_result["data"])
            elif "defects" in batch_result and isinstance(batch_result["defects"], list):
                if "defects" not in all_results:
                    all_results["defects"] = []
                all_results["defects"].extend(batch_result["defects"])
        
        return all_results

    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """发送HTTP请求核心方法"""
        url = f"{self.base_url}{endpoint}"

        try:
            # 确保数据正确编码
            if 'json' in kwargs:
                kwargs['data'] = json.dumps(kwargs.pop('json'), ensure_ascii=False).encode('utf-8')
                kwargs.setdefault('headers', {})['Content-Type'] = 'application/json; charset=utf-8'

            response = self.session.request(
                method=method,
                url=url,
                timeout=self.timeout,
                **kwargs
            )

            logger.debug(f"API请求: {method} {url} -> {response.status_code}")

            if response.status_code == 200:
                return {
                    "success": True,
                    "data": response.json(),
                    "status_code": response.status_code
                }
            else:
                error_msg = f"API错误: {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get('error', error_msg)
                except:
                    error_msg = response.text or error_msg

                return {
                    "success": False,
                    "error": error_msg,
                    "status_code": response.status_code
                }

        except requests.exceptions.ConnectionError:
            error_msg = f"无法连接到后端服务: {self.base_url}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "status_code": 0
            }
        except Exception as e:
            error_msg = f"请求异常: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "status_code": 0
            }

    def health_check(self) -> Dict[str, Any]:
        """健康检查API"""
        return self._request('GET', '/api/health')

    def fix_code(self, code: str, defects: list = None, language: str = "python", level: str = "standard") -> Dict[str, Any]:
        """代码修复API - 适配后端路由 /api/fix-code"""
        payload = {
            "code": code,
            "language": language,
            "level": level
        }
        
        # 如果有缺陷数据，添加到payload
        if defects:
            payload["defects"] = defects
            
        result = self._request('POST', '/api/fix-code', json=payload)
        
        # 适配后端响应格式变化，确保修复后的代码和变更在响应顶层
        if result.get("success") and "data" in result:
            data = result["data"]
            # 将data中的字段提升到结果顶层
            result.update(data)
            # 保留原始的data字段以保持向后兼容
        
        return result

    def analyze_code(self, code: str, file_name: str = "code.py") -> Dict[str, Any]:
        """代码分析API - 适配后端路由 /api/analyze-code"""
        payload = {"code": code, "file_name": file_name}
        result = self._request('POST', '/api/analyze-code', json=payload)
        
        # 适配后端响应格式变化，确保分析结果在响应顶层
        if result.get("success") and "data" in result:
            data = result["data"]
            # 将data中的字段提升到结果顶层
            result.update(data)
            # 保留原始的data字段以保持向后兼容
        
        return result

    def generate_repair_plan(self, defects: list) -> Dict[str, Any]:
        """生成修复计划API - 适配后端路由 /api/generate-plan"""
        payload = {
            "defects": defects
        }
        result = self._request('POST', '/api/generate-plan', json=payload)
        
        if result.get("success") and "data" in result:
            data = result["data"]
            result.update(data)
        
        return result

    def upload_files(self, files, is_folder: bool = False) -> Dict[str, Any]:
        """上传文件API - 适配后端路由 /api/upload
        
        Args:
            files: 文件列表，每个元素是一个元组，包含文件名和文件内容
            is_folder: 是否为文件夹上传
        """
        # 检查是否为传统的files参数（元组列表）
        if isinstance(files, list) and files and isinstance(files[0], tuple):
            # 准备文件数据，过滤超大文件
            files_data = self._prepare_files_data(files)
            
            # 添加上传类型标识
            payload = {
                "files": files_data,
                "is_folder": is_folder
            }
            
            # 对于文件夹或大量文件，使用批处理
            if is_folder or len(files_data) > self.max_batch_size:
                return self._batch_process("/api/upload", "files", files_data)
            
            # 直接上传
            return self._request('POST', '/api/upload', json=payload)
        
        # 兼容原有代码，使用传统的files参数
        return self._request('POST', '/api/upload', files=files)

    def analyze_project(self, project_data) -> Dict[str, Any]:
        """项目分析API - 适配后端路由 /api/analyze-project"""
        # 检查输入格式
        if isinstance(project_data, dict) and 'files' in project_data:
            # 使用批处理函数处理大量文件
            return self._batch_process("/api/analyze-project", "files", project_data['files'])
        
        # 兼容原有代码，使用文件上传方式
        if isinstance(project_data, list) and project_data and isinstance(project_data[0], tuple):
            return self._request('POST', '/api/analyze-project', files=project_data)
        
        # 使用JSON格式
        return self._request('POST', '/api/analyze-project', json=project_data)

    def batch_fix(self, project_data: dict) -> Dict[str, Any]:
        """批量修复API - 适配后端路由 /api/batch-fix"""
        # 对于大量文件使用批处理
        if isinstance(project_data, dict) and 'files' in project_data and len(project_data['files']) > self.max_batch_size:
            return self._batch_process("/api/batch-fix", "files", project_data['files'])
            
        result = self._request('POST', '/api/batch-fix', json=project_data)
        
        if result.get("success") and "data" in result:
            data = result["data"]
            result.update(data)
        
        return result

    def handle_folder_upload(self, folder_content: List[Dict]) -> Dict[str, Any]:
        """处理文件夹上传，支持大型文件夹结构"""
        try:
            # 提取文件数据
            files = [(item['file_name'], item['content']) for item in folder_content]
            
            # 使用批处理上传
            return self.upload_files(files, is_folder=True)
        except Exception as e:
            error_msg = f"文件夹上传处理失败: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "status_code": 0
            }

    def update_base_url(self, new_url: str):
        """更新基础URL"""
        self.base_url = new_url.rstrip('/')
        logger.info(f"更新后端URL: {self.base_url}")