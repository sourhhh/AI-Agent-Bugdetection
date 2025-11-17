"""
文件上传组件 - 提供批量文件处理功能
"""
import gradio as gr
import os


def create_file_uploader(backend_service):
    """创建文件上传组件"""

    with gr.Column():
        gr.Markdown("### 📁 批量文件处理")

        upload_type = gr.Radio(
            label="上传类型",
            choices=["单个/多个文件", "整个文件夹"],
            value="单个/多个文件"
        )
        
        file_upload = gr.File(
            label="上传代码文件",
            file_count="multiple",
            file_types=[".py", ".js", ".java", ".cpp", ".txt"],
            type="filepath"
        )
        
        folder_upload = gr.Files(
            label="上传整个文件夹",
            file_count="directory",
            type="filepath"
        )

        process_btn = gr.Button("🚀 批量处理", variant="primary")

        with gr.Row():
            progress = gr.HTML(label="处理进度")

        results_display = gr.Dataframe(
            label="分析结果",
            headers=["文件名", "状态", "缺陷数", "错误信息"],
            interactive=False,

        )

    def process_files(upload_type, file_upload, folder_upload):
        """处理上传的文件或文件夹"""
        # 根据上传类型选择文件列表
        if upload_type == "单个/多个文件":
            files = file_upload
        else:
            files = folder_upload

        if not files:
            return "<div style='color: orange;'>⚠️ 请先上传文件或文件夹</div>", []

        results = []
        progress_html = "<div>"

        # 过滤支持的文件类型
        supported_extensions = ['.py', '.js', '.java', '.cpp', '.txt']
        valid_files = []
        
        for file_info in files:
            file_path = file_info.name
            file_ext = os.path.splitext(file_path)[1].lower()
            if file_ext in supported_extensions:
                valid_files.append(file_info)

        if not valid_files:
            return "<div style='color: orange;'>⚠️ 未找到支持的代码文件</div>", []

        progress_html += f"<div>找到 {len(valid_files)} 个支持的文件</div>"

        # 如果文件数量过多，使用批量分析API
        if len(valid_files) > 3:
            try:
                # 准备批量分析数据
                files_data = []
                for file_info in valid_files:
                    file_path = file_info.name
                    filename = os.path.basename(file_path)
                    
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    files_data.append({"name": filename, "content": content})

                # 调用批量分析API
                result = backend_service.analyze_project({"files": files_data})
                
                if result.get("success"):
                    # 处理批量分析结果
                    defects_by_file = {}
                    
                    # 按文件名组织缺陷
                    if "defects" in result:
                        for defect in result["defects"]:
                            # 假设缺陷信息中包含文件名
                            filename = defect.get("file_path", "未知文件")
                            if filename not in defects_by_file:
                                defects_by_file[filename] = []
                            defects_by_file[filename].append(defect)
                    
                    # 生成结果表格
                    for file_info in valid_files:
                        filename = os.path.basename(file_info.name)
                        file_defects = defects_by_file.get(filename, [])
                        results.append([filename, "✅ 分析完成", len(file_defects), ""])
                    
                    progress_html += "<div style='color: green;'>✅ 批量分析完成</div>"
                else:
                    progress_html += f"<div style='color: red;'>❌ 批量分析失败: {result.get('error', '未知错误')}</div>"
                    # 回退到单个文件分析
                    valid_files = []
            except Exception as e:
                progress_html += f"<div style='color: orange;'>⚠️ 批量分析失败，回退到单个文件分析: {str(e)}</div>"
                # 继续单个文件分析

        # 单个文件分析（用于少量文件或批量分析失败时）
        if valid_files:
            for i, file_info in enumerate(valid_files):
                file_path = file_info.name
                filename = os.path.basename(file_path)

                try:
                    # 读取文件内容
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()

                    # 调用代码分析服务
                    result = backend_service.analyze_code(content)

                    if result["success"]:
                        defects = result.get("defects", [])
                        status = f"✅ 发现{len(defects)}个缺陷"
                        fixes = len(defects)  # 显示缺陷数量
                        error = ""
                    else:
                        status = "❌ 失败"
                        fixes = 0
                        error = result.get("error", "未知错误")

                    results.append([filename, status, fixes, error])
                    progress_html += f"<div>{i + 1}. {filename}: {status}</div>"

                except UnicodeDecodeError:
                    results.append([filename, "❌ 错误", 0, "无法解码文件内容（可能是二进制文件）"])
                    progress_html += f"<div style='color: red;'>{i + 1}. {filename}: 无法解码文件</div>"
                except Exception as e:
                    results.append([filename, "❌ 错误", 0, str(e)])
                    progress_html += f"<div style='color: red;'>{i + 1}. {filename}: 错误 - {str(e)}</div>"

        progress_html += "</div>"
        return progress_html, results

    # 连接事件
    process_btn.click(
        fn=process_files,
        inputs=[upload_type, file_upload, folder_upload],
        outputs=[progress, results_display]
    )
    
    # 控制显示/隐藏文件和文件夹上传组件
    def update_upload_visibility(upload_type):
        if upload_type == "单个/多个文件":
            return gr.update(visible=True), gr.update(visible=False)
        else:
            return gr.update(visible=False), gr.update(visible=True)
    
    upload_type.change(
        fn=update_upload_visibility,
        inputs=upload_type,
        outputs=[file_upload, folder_upload]
    )

    return {
        "upload_type": upload_type,
        "file_upload": file_upload,
        "folder_upload": folder_upload,
        "process_btn": process_btn,
        "results_display": results_display
    }