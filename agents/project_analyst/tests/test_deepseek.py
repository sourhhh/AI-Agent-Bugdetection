import os
import unittest
from unittest.mock import patch, Mock
from agentcode.deepseek import DeepSeekClient

class TestDeepSeekClient(unittest.TestCase):
    """测试DeepSeekClient类的功能"""
    
    def setUp(self):
        """测试前准备配置和环境"""
        # 保存原始环境变量以便测试后恢复
        self.original_api_key = os.getenv("DEEPSEEK_API_KEY")
        
        # 测试配置
        self.test_config = {
            "deepseek": {
                "api_base": "https://api.test.deepseek.com",
                "model": "test-model",
                "timeout": 30,
                "chunk_size": 5
            }
        }
    
    def tearDown(self):
        """测试后恢复环境变量"""
        if self.original_api_key is not None:
            os.environ["DEEPSEEK_API_KEY"] = self.original_api_key
        else:
            os.environ.pop("DEEPSEEK_API_KEY", None)
    
    @patch("agentcode.deepseek.load_config")
    def test_api_key_loading(self, mock_load_config):
        """测试API密钥加载逻辑"""
        # 配置模拟
        mock_load_config.return_value = self.test_config
        
        # 测试1: 直接提供API密钥
        client = DeepSeekClient(api_key="direct_test_key")
        self.assertEqual(client.api_key, "direct_test_key")
        
        # 测试2: 从环境变量加载
        os.environ["DEEPSEEK_API_KEY"] = "env_test_key"
        client = DeepSeekClient()
        self.assertEqual(client.api_key, "env_test_key")
        
        # 测试3: 无API密钥的情况
        os.environ.pop("DEEPSEEK_API_KEY", None)
        client = DeepSeekClient()
        self.assertIsNone(client.api_key)
    
    @patch("agentcode.deepseek.load_config")
    def test_config_validation(self, mock_load_config):
        """测试配置验证功能"""
        # 测试1: 配置完整的情况
        mock_load_config.return_value = self.test_config
        client = DeepSeekClient(api_key="test_key")  # 不应抛出异常
        
        # 测试2: 缺失必要配置项
        invalid_config = {"deepseek": {"api_base": "https://api.test.deepseek.com"}}  # 缺少model等
        mock_load_config.return_value = invalid_config
        
        with self.assertRaises(ValueError) as context:
            DeepSeekClient(api_key="test_key")
        self.assertIn("缺失必要项", str(context.exception))
    
    @patch("agentcode.deepseek.requests.post")
    @patch("agentcode.deepseek.load_config")
    def test_api_request(self, mock_load_config, mock_post):
        """测试API请求功能"""
        # 配置模拟
        mock_load_config.return_value = self.test_config
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Test response content"}}]
        }
        mock_post.return_value = mock_response
        
        # 测试正常请求
        client = DeepSeekClient(api_key="test_key")
        result = client._post_request("Test prompt")
        self.assertEqual(result, "Test response content")
        
        # 验证请求参数
        mock_post.assert_called_once_with(
            f"{self.test_config['deepseek']['api_base']}/chat/completions",
            headers={"Authorization": "Bearer test_key"},
            json={
                "model": self.test_config["deepseek"]["model"],
                "messages": [
                    {"role": "system", "content": "你是专业的代码分析助手，需准确解析项目结构和逻辑"},
                    {"role": "user", "content": "Test prompt"}
                ]
            },
            timeout=self.test_config["deepseek"]["timeout"]
        )
    
    @patch("agentcode.deepseek.load_config")
    def test_no_api_key_handling(self, mock_load_config):
        """测试无API密钥时的错误处理"""
        mock_load_config.return_value = self.test_config
        os.environ.pop("DEEPSEEK_API_KEY", None)  # 确保没有环境变量
        
        client = DeepSeekClient()
        result = client._post_request("Test prompt")
        self.assertEqual(result, "错误：未设置DEEPSEEK_API_KEY环境变量")
    
    @patch("agentcode.deepseek.requests.post")
    @patch("agentcode.deepseek.load_config")
    def test_api_error_handling(self, mock_load_config, mock_post):
        """测试API调用错误处理"""
        mock_load_config.return_value = self.test_config
        mock_post.side_effect = Exception("Connection error")  # 模拟连接错误
        
        client = DeepSeekClient(api_key="test_key")
        result = client._post_request("Test prompt")
        self.assertIn("API调用失败: Connection error", result)
