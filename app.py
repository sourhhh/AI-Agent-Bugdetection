# code_fixer_backend/app.py
from flask import Flask, send_from_directory
from flask_cors import CORS
from config.settings import Config
from api_new.routes import api_blueprint
import logging


def create_app():
    """创建Flask应用工厂函数"""
    app = Flask(__name__)

    # 加载配置
    app.config.from_object(Config)

    # 配置CORS
    CORS(app, resources={
        r"/api/*": {
            "origins": Config.CORS_ORIGINS,
            "methods": ["GET", "POST", "PUT", "DELETE"],
            "allow_headers": ["Content-Type", "Authorization"]
        }
    })

    # 注册蓝图
    app.register_blueprint(api_blueprint, url_prefix='/api')

    # 静态托管 pipeline demo 页面
    @app.route('/pipeline-demo')
    def pipeline_demo_index():
        return send_from_directory('../frontend/pipeline_demo', 'index.html')

    @app.route('/pipeline-demo/<path:p>')
    def pipeline_demo_static(p):
        return send_from_directory('../frontend/pipeline_demo', p)

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    return app


if __name__ == '__main__':
    app = create_app()

    print("🚀 代码修复后端服务启动成功!")
    print("📍 服务地址: http://localhost:5000")
    print("📚 API文档:")
    print("  健康检查: GET  /api/health")
    print("  代码修复: POST /api/fix-code")
    print("  代码分析: POST /api/analyze-code")
    print("  生成计划: POST /api/generate-plan")
    print("  文件上传: POST /api/upload-files")
    print("  项目分析: POST /api/analyze-project")

    app.run(
        host='0.0.0.0',
        port=5000,
        debug=Config.DEBUG
    )