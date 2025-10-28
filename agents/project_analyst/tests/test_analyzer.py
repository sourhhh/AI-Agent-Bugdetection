import os
import tempfile
import shutil
from agentcode.analyzer import ProjectAnalyst
from agentcode.schemas.project_context import ProjectContext

class TestProjectAnalyst:
    """测试ProjectAnalyst类的核心功能"""
    
    def setup_method(self):
        """测试前创建临时项目目录"""
        self.test_dir = tempfile.mkdtemp()
        self.sample_files = [
            "main.py",                  # 入口文件
            "utils/helper.py",          # 普通模块
            "tests/test_case.py",        # 测试文件
            "requirements.txt",          # 依赖文件
            "pyproject.toml"            # 现代依赖文件
        ]
        
        # 创建测试文件结构
        for file_path in self.sample_files:
            full_path = os.path.join(self.test_dir, file_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                if file_path == "main.py":
                    # 添加入口文件标识
                    f.write('if __name__ == "__main__":\n    print("Hello World")')
                else:
                    f.write("# Sample content")
    
    def teardown_method(self):
        """测试后清理临时目录"""
        shutil.rmtree(self.test_dir)
    
    def test_project_context_extraction(self):
        """测试项目上下文信息提取"""
        analyst = ProjectAnalyst(project_path=self.test_dir, use_deepseek=False)
        result = analyst.analyze()
        context = result["project_context"]
        
        # 验证项目根目录正确
        assert context["project_root"] == self.test_dir
        
        # 验证Python文件识别
        python_files = [os.path.basename(path) for path in context["python_files"]]
        assert "main.py" in python_files
        assert "helper.py" in python_files
        assert "test_case.py" in python_files
        
        # 验证测试目录识别
        assert any("test" in os.path.basename(path) for path in context["test_directories"])
        
        # 验证入口文件识别
        assert any("main.py" in path for path in context["entry_points"])
        
        # 验证依赖文件识别
        assert len(context["requirements_path"]) > 0
    
    def test_exclude_paths(self):
        """测试路径排除功能"""
        analyst = ProjectAnalyst(
            project_path=self.test_dir,
            use_deepseek=False,
            exclude_paths=["test", "utils"]  # 排除测试目录和工具目录
        )
        result = analyst.analyze()
        context = result["project_context"]
        
        # 验证被排除的路径不在结果中
        python_files = [os.path.basename(path) for path in context["python_files"]]
        assert "helper.py" not in python_files  # 已被排除
        assert "test_case.py" not in python_files  # 已被排除
        assert "main.py" in python_files  # 应保留
