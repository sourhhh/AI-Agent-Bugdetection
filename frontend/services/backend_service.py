"""
后端服务客户端
"""
import requests
import json
import logging

logger = logging.getLogger(__name__)

# 使用相对导入
from .api_client import APIClient


class BackendService:
    """后端服务客户端"""

    def __init__(self, base_url=None):
        # 确保 base_url 被设置为实例属性
        if base_url is None:
            try:
                from config import Config
                self.base_url = Config.BACKEND_URL
            except ImportError:
                # 如果导入失败，使用默认值
                self.base_url = "http://localhost:5000"
        else:
            self.base_url = base_url

        # 确保 base_url 是字符串且没有尾随斜杠
        self.base_url = str(self.base_url).rstrip('/')

        # 初始化 API 客户端
        self.api_client = APIClient(self.base_url)

        logger.info(f"BackendService 初始化完成，后端URL: {self.base_url}")

    def fix_code(self, code, options):
        """修复代码"""
        try:
            # 适配后端API，现在需要先分析获取缺陷报告
            if "defects" not in options:
                # 先进行代码分析获取缺陷报告
                analyze_result = self.analyze_code(code)
                if not analyze_result.get("success"):
                    return analyze_result
                
                # 从分析结果中获取缺陷数据
                defects = analyze_result.get("defects", [])
                options["defects"] = defects
            
            result = self.api_client.fix_code(code, options.get("defects"))
            return result

        except Exception as e:
            logger.error(f"修复代码失败: {str(e)}")
            return {
                "success": False,
                "error": f"请求失败: {str(e)}"
            }

    def analyze_code(self, code):
        """分析代码"""
        try:
            result = self.api_client.analyze_code(code)
            return result

        except Exception as e:
            logger.error(f"分析代码失败: {str(e)}")
            return {
                "success": False,
                "error": f"分析请求失败: {str(e)}"
            }

    def check_connection(self):
        """检查后端连接状态"""
        try:
            result = self.api_client.health_check()
            if result.get("success"):
                return "✅ 后端服务连接正常"
            else:
                # 尝试直接连接测试
                try:
                    test_response = requests.get(f"{self.base_url}/api/health", timeout=5)
                    if test_response.status_code == 200:
                        return "✅ 后端服务连接正常（健康检查API格式不匹配）"
                    else:
                        return f"❌ 后端服务响应异常: {test_response.status_code}"
                except requests.exceptions.ConnectionError:
                    return f"❌ 无法连接到后端服务: {self.base_url} - 请确保后端服务正在运行"
                except Exception as e:
                    return f"❌ 连接测试失败: {str(e)}"
        except Exception as e:
            return f"❌ 连接检查异常: {str(e)}"

    def generate_repair_plan(self, defects):
        """生成修复计划"""
        try:
            result = self.api_client.generate_repair_plan(defects)
            return result
        except Exception as e:
            logger.error(f"生成修复计划失败: {str(e)}")
            return {
                "success": False,
                "error": f"生成计划失败: {str(e)}"
            }
    
    def upload_files(self, files):
        """上传文件"""
        try:
            result = self.api_client.upload_files(files)
            return result
        except Exception as e:
            logger.error(f"文件上传失败: {str(e)}")
            return {
                "success": False,
                "error": f"上传失败: {str(e)}"
            }
    
    def analyze_project(self, project_data):
        """分析整个项目"""
        try:
            # 确保数据格式正确
            if isinstance(project_data, dict) and 'files' in project_data:
                # 对于大量文件，分批处理以避免请求过大
                files = project_data['files']
                batch_size = 10  # 每批处理10个文件
                all_results = {"success": True, "defects": [], "total_files": len(files)}
                
                # 如果文件数量较少，直接处理
                if len(files) <= batch_size:
                    result = self.api_client.analyze_project(project_data)
                    return result
                
                # 分批处理
                for i in range(0, len(files), batch_size):
                    batch = files[i:i+batch_size]
                    batch_result = self.api_client.analyze_project({"files": batch})
                    
                    if not batch_result.get("success"):
                        all_results["success"] = False
                        all_results["error"] = batch_result.get("error", "批处理失败")
                        break
                    
                    # 合并缺陷结果
                    if "defects" in batch_result:
                        all_results["defects"].extend(batch_result["defects"])
                
                return all_results
            else:
                # 如果数据格式不正确，尝试直接调用
                result = self.api_client.analyze_project(project_data)
                return result
        except Exception as e:
            logger.error(f"项目分析失败: {str(e)}")
            return {
                "success": False,
                "error": f"项目分析失败: {str(e)}"
            }
    
    def batch_fix(self, project_data):
        """批量修复"""
        try:
            result = self.api_client.batch_fix(project_data)
            return result
        except Exception as e:
            logger.error(f"批量修复失败: {str(e)}")
            return {
                "success": False,
                "error": f"批量修复失败: {str(e)}"
            }
    
    def update_base_url(self, new_url):
        """更新后端URL"""
        self.base_url = new_url.rstrip('/')
        self.api_client.update_base_url(new_url)
        return f"✅ 后端URL已更新: {new_url}"


if __name__ == "__main__":
    # 测试
    service = BackendService("http://localhost:5000")
    print("BackendService 初始化成功")
    print(f"base_url: {service.base_url}")