"""
代码编辑器组件 - 提供代码编辑、修复、分析功能
"""
import gradio as gr
from typing import Dict, Any


def create_code_editor(backend_service, mode: str = "fix"):
    """创建代码编辑器组件"""

    with gr.Row():
        with gr.Column(scale=1):
            # 输入区域
            code_input = gr.Code(
                label="📝 输入代码",
                language="python",
                value='def example():\n    prinnt("Hello, World!")\n    return eval("1+1")',
                lines=15,
                interactive=True
            )

            # 简化设置，后端会自动处理语言检测
            language = gr.Dropdown(
                choices=["python", "javascript", "java", "cpp"],
                value="python",
                label="编程语言"
            )

            if mode == "fix":
                action_btn = gr.Button("🔧 修复代码", variant="primary", size="lg")
            else:
                action_btn = gr.Button("📊 分析代码", variant="secondary", size="lg")

            clear_btn = gr.Button("🗑️ 清空", variant="secondary")

        with gr.Column(scale=1):
            # 输出区域
            if mode == "fix":
                code_output = gr.Code(
                    label="✅ 修复结果",
                    language="python",
                    lines=15,
                    interactive=False
                )
            else:
                code_output = gr.JSON(
                    label="📋 分析结果",
                    visible=True
                )

            result_message = gr.Textbox(
                label="操作结果",
                interactive=False,
                show_label=True
            )

    # 事件处理函数
    def handle_action(code, lang=None):
        """处理代码修复或分析操作"""
        if not code.strip():
            return "", "❌ 请输入代码"

        if mode == "fix":
            # 修复流程：先分析获取缺陷，然后修复
            # 注意：backend_service.fix_code 现在会自动处理分析步骤
            result = backend_service.fix_code(code, {})
            
            if result["success"]:
                fixed_code = result.get("fixed_code", "")
                changes_count = result.get("changes_count", 0)
                return fixed_code, f"✅ 修复完成! 共{changes_count}处变更"
            else:
                error_msg = result.get("error", "未知错误")
                return "", f"❌ {error_msg}"
        else:
            # 分析流程
            result = backend_service.analyze_code(code)
            
            if result["success"]:
                defects = result.get("defects", [])
                analysis_summary = {
                    "success": True,
                    "defects": defects,
                    "defects_count": len(defects),
                    "analysis_time": result.get("analysis_time", 0)
                }
                return analysis_summary, f"✅ 分析完成! 发现{len(defects)}个缺陷"
            else:
                error_msg = result.get("error", "未知错误")
                return {"success": False, "error": error_msg}, f"❌ {error_msg}"

    # 连接事件
    action_btn.click(
        fn=handle_action,
        inputs=[code_input, language],
        outputs=[code_output, result_message]
    )

    clear_btn.click(
        fn=lambda: ("", ""),
        outputs=[code_input, result_message]
    )

    return {
        "code_input": code_input,
        "code_output": code_output,
        "action_btn": action_btn
    }