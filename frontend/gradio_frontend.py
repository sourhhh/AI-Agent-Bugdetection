"""
Gradio前端主应用 - 提供用户界面并与后端API交互
"""
import gradio as gr
import os
import sys
import io
from typing import List, Dict, Any, Tuple
from services.backend_service import BackendService
from services.backend_manager import BackendManager
from components.code_editor import create_code_editor
from components.result_display import create_result_display
from utils.helpers import setup_logging
from config import Config


def handle_file_upload(backend_service, files):
    """处理文件上传"""
    if not files:
        return "请选择要上传的文件"
    
    # 准备上传的文件数据
    upload_files = []
    for file in files:
        with open(file.name, 'rb') as f:
            content = f.read()
            upload_files.append((os.path.basename(file.name), content))
    
    result = backend_service.upload_files(upload_files)
    
    if result.get("success"):
        return f"✅ 文件上传成功！共上传 {len(files)} 个文件"
    else:
        return f"❌ 上传失败: {result.get('error', '未知错误')}"


def handle_project_analysis(backend_service, files):
    """处理项目分析"""
    if not files:
        return "请选择要分析的文件", {}
    
    # 准备上传的文件数据
    upload_files = []
    for file in files:
        with open(file.name, 'rb') as f:
            content = f.read()
            upload_files.append((os.path.basename(file.name), content))
    
    result = backend_service.analyze_project(upload_files)
    
    if result.get("success"):
        # 格式化分析结果
        summary = f"✅ 项目分析完成！\n\n"
        summary += f"缺陷总数: {len(result.get('defects', []))}\n"
        summary += f"文件数: {len(files)}"
        return summary, result
    else:
        return f"❌ 分析失败: {result.get('error', '未知错误')}", {}


def handle_batch_fix(backend_manager, analysis_result, terminal_output):
    """处理批量修复 - 直接运行后端run_full_pipeline.py文件"""
    # 清除终端输出历史
    terminal_output.value = ""
    
    # 定义输出回调函数
    def output_handler(line):
        terminal_output.value += line + "\n"
    
    # 只运行run_full_pipeline.py文件
    file_name = "run_full_pipeline.py"
    output_handler(f"\n🚀 正在运行: {file_name}\n")
    
    # 运行后端文件
    result = backend_manager.run_backend_file(
        file_name=file_name,
        output_callback=output_handler,
        args=["--batch-mode"]
    )
    
    # 生成总结
    summary = f"\n📊 批量修复任务完成！\n\n"
    if result.get("success"):
        summary += f"✅ {file_name} 执行成功\n"
        summary += "🎉 批量修复已完成，请查看终端输出了解详情！"
    else:
        summary += f"❌ {file_name} 执行失败\n"
        summary += f"⚠️ 错误信息: {result.get('message', '未知错误')}"
    
    return summary, terminal_output.value


def create_interface():
    """创建Gradio界面主函数"""

    # 初始化后端服务
    backend_service = BackendService()
    
    # 初始化后端管理器
    backend_manager = BackendManager()
    
    # 全局状态
    backend_process = gr.State(None)
    terminal_history = gr.State("")

    # 设置日志
    logger = setup_logging()

    with gr.Blocks(
            theme=gr.themes.Soft(),
            title="AI代码修复系统",
            css="""
        .success { color: #00aa00; font-weight: bold; }
        .error { color: #ff4444; font-weight: bold; }
        .warning { color: #ffaa00; font-weight: bold; }
        """
    ) as demo:
        gr.Markdown("""
        # 🤖 AI代码修复系统
        **基于深度学习的智能代码缺陷检测和自动修复工具**
        """)

        # 连接状态显示
        with gr.Row():
            status_display = gr.Textbox(
                label="🔗 后端连接状态",
                value="检查中...",
                interactive=False
            )
            refresh_btn = gr.Button("🔄 刷新状态", size="sm")

        # 主功能标签页
        with gr.Tab("💻 代码修复"):
            code_editor_component = create_code_editor(backend_service, mode="fix")

        with gr.Tab("📊 代码分析"):
            with gr.Row():
                with gr.Column(scale=2):
                    code_editor_component = create_code_editor(backend_service, mode="analyze")
                with gr.Column(scale=3):
                    # 创建结果展示组件
                    analysis_result_components = create_result_display(backend_service)

        with gr.Tab("📁 项目分析"):
            gr.Markdown("## 项目代码分析")
            
            with gr.Row():
                files_input = gr.File(
                    label="选择项目文件",
                    file_types=[".py", ".js", ".ts", ".cpp", ".java"],
                    file_count="multiple"
                )
            
            with gr.Row():
                analyze_button = gr.Button("开始分析", variant="primary")
                upload_button = gr.Button("仅上传文件")
            
            analysis_status = gr.Textbox(label="分析状态", interactive=False)
            analysis_result = gr.State({})  # 存储分析结果
            
            # 创建结果展示组件
            project_result_components = create_result_display(backend_service)
            
            # 文件上传事件
            upload_button.click(
                fn=lambda files: handle_file_upload(backend_service, files),
                inputs=[files_input],
                outputs=[analysis_status]
            )
            
            # 更新handle_project_analysis函数以支持结果展示组件
            def enhanced_project_analysis(files):
                """增强版项目分析处理函数"""
                status, result = handle_project_analysis(backend_service, files)
                
                if not result or not isinstance(result, dict) or not result.get("success"):
                    return (status, result, 
                            "<div style='color: red;'>分析失败，请查看状态信息</div>", 
                            gr.update(), {}, ["全部"], [], [])
                
                # 使用结果展示组件处理数据
                update_func = project_result_components["update_result_display"]
                summary, table_data, report_data, types, defects, filtered_defects = update_func(result)
                
                return (status, result, summary, table_data, report_data, types, defects, filtered_defects)
            
            # 项目分析事件
            analyze_button.click(
                fn=enhanced_project_analysis,
                inputs=[files_input],
                outputs=[
                    analysis_status, 
                    analysis_result,
                    project_result_components["summary_html"],
                    project_result_components["defect_table"],
                    project_result_components["raw_report"],
                    project_result_components["type_filter"],
                    project_result_components["defects_state"],
                    project_result_components["filtered_defects_state"]
                ]
            )

        with gr.Tab("🔧 批量修复"):
            gr.Markdown("## 批量代码修复")
            
            batch_status = gr.Textbox(label="修复状态", interactive=False)
            batch_fix_button = gr.Button("开始批量修复", variant="primary")
            
            # 添加终端输出组件
            gr.Markdown("## 运行结果输出")
            batch_terminal_output = gr.Code(label="终端输出", language="text", lines=15, interactive=False)
            
            # 批量终端输出状态变量
            batch_terminal_history = gr.State("")
            
            # 批量修复事件 - 移除对项目分析结果的依赖
            batch_fix_button.click(
                fn=lambda history: handle_batch_fix(backend_manager, None, history),
                inputs=[batch_terminal_history],
                outputs=[batch_status, batch_terminal_output]
            )

        with gr.Tab("❤️ 健康检查"):
            gr.Markdown("## 系统健康状态")
            
            health_status = gr.Textbox(label="后端服务状态", interactive=False)
            health_check_button = gr.Button("检查健康状态", variant="primary")
            
            gr.Markdown("## 后端终端输出")
            terminal_output = gr.Code(label="终端输出", language="text", lines=10, interactive=False)
            
            # 健康检查事件
            health_check_button.click(
                fn=backend_service.check_connection,
                outputs=[health_status]
            )

        with gr.Tab("⚙️ 设置"):
            with gr.Row():
                with gr.Column():
                    gr.Markdown("### 后端配置")
                    backend_url = gr.Textbox(
                        label="后端API地址",
                        value=Config.BACKEND_URL,
                        placeholder="http://localhost:5000"
                    )
                    save_config_btn = gr.Button("💾 保存配置")
                
                with gr.Column():
                    gr.Markdown("### 后端服务控制")
                    start_backend_btn = gr.Button("🚀 启动后端服务", variant="primary")
                    stop_backend_btn = gr.Button("🛑 停止后端服务", variant="stop")
                    backend_status = gr.Textbox(label="服务状态", value="未启动", interactive=False)

        # 事件处理
        refresh_btn.click(
            fn=backend_service.check_connection,
            outputs=status_display
        )
        
        # 后端控制事件
        start_backend_btn.click(
            fn=handle_start_backend,
            outputs=[backend_status, health_status]
        )
        
        stop_backend_btn.click(
            fn=handle_stop_backend,
            outputs=[backend_status, health_status]
        )
        
        # 创建一个隐藏的按钮用于定时刷新
        refresh_timer = gr.Button(visible=False)
        
        # 刷新批量修复终端输出
        def refresh_batch_terminal_output():
            """刷新批量修复终端输出显示"""
            return batch_terminal_history.value
        
        # 设置定时刷新（每3秒）
        refresh_timer.click(
            fn=lambda: (
                periodic_refresh()[0],  # 后端状态
                periodic_refresh()[1],  # 终端输出
                refresh_batch_terminal_output()  # 批量修复终端输出
            ),
            outputs=[backend_status, terminal_output, batch_terminal_output],
            every=3  # 每3秒执行一次
        )
        
        # 初始化显示
        demo.load(
            fn=lambda: (update_backend_status(), ""),
            outputs=[backend_status, terminal_output]
        )
        
        # 健康检查时也更新后端状态
        health_check_button.click(
            fn=lambda: (
                backend_service.check_connection(),
                update_backend_status()
            ),
            outputs=[health_status, backend_status]
        )

        # 初始化连接状态
        demo.load(
            fn=backend_service.check_connection,
            outputs=status_display
        )

        # 配置保存
        def save_backend_config(url):
            backend_service.update_base_url(url)
            return f"✅ 配置已更新: {url}"
            
        # 后端启动处理函数
        def handle_start_backend():
            """处理后端启动"""
            # 全局终端历史
            terminal_history.value = ""
            
            # 定义输出回调函数
            def output_handler(line):
                if hasattr(terminal_history, 'value'):
                    terminal_history.value += line + "\n"
                    # 更新终端显示
                    if 'terminal_output' in locals():
                        terminal_output.value = terminal_history.value
            
            # 启动后端
            result = backend_manager.start_backend(output_callback=output_handler)
            
            if result["success"]:
                return "运行中", result["message"]
            else:
                return "未启动", result["message"]
        
        # 后端停止处理函数
        def handle_stop_backend():
            """处理后端停止"""
            result = backend_manager.stop_backend()
            
            if result["success"]:
                return "未启动", result["message"]
            else:
                # 检查实际状态
                status = backend_manager.get_status()
                return status["status"], result["message"]
        
        # 更新后端状态
        def update_backend_status():
            """更新后端状态显示"""
            status = backend_manager.get_status()
            return status["status"]
            
        # 刷新终端输出
        def refresh_terminal_output():
            """刷新终端输出显示"""
            return terminal_history.value
            
        # 定时刷新函数
        def periodic_refresh():
            """定期刷新状态和输出"""
            return (
                update_backend_status(),
                refresh_terminal_output()
            )

        save_config_btn.click(
            fn=save_backend_config,
            inputs=backend_url,
            outputs=status_display
        )

    return demo


if __name__ == "__main__":
    # 启动Gradio应用
    demo = create_interface()
    demo.launch(
        server_name="0.0.0.0",
        server_port=Config.GRADIO_SERVER_PORT,
        share=Config.GRADIO_SHARE,
        show_error=True,
        inbrowser=True  # 自动打开浏览器
    )