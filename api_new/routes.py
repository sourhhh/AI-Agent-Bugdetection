# code_fixer_backend/api/routes.py
from flask import Blueprint, request, jsonify, send_file, abort
import logging
import json
import os
from werkzeug.utils import secure_filename
from typing import Dict, List

# 导入你的现有模块
from agents.code_fixer import CodeFixerAgent
from agents.decision_manager import DecisionManagerAgent
from schemas.defect_report import DefectReport, FileDefects, Defect
from schemas.repair_plan import RepairPlan
from services_new.analysis_service import AnalysisService
from services_new import pipeline_service

api_blueprint = Blueprint('api', __name__)
logger = logging.getLogger(__name__)

# 初始化Agent与服务
code_fixer = CodeFixerAgent()
decision_manager = DecisionManagerAgent()
analysis_service = AnalysisService()


@api_blueprint.route('/health', methods=['GET'])
def health_check():
    """健康检查端点"""
    import os
    ai_available = bool(os.getenv('DEEPSEEK_API_KEY'))
    return jsonify({
        "status": "healthy",
        "service": "code-fixer-backend",
        "version": "1.0.0",
        "ai_available": ai_available
    })


@api_blueprint.route('/fix-code', methods=['POST'])
def fix_code():
    """
    代码修复API
    接收: { "code": "代码内容", "defects": "缺陷报告JSON" }
    返回: { "success": true, "fixed_code": "修复后代码", "changes": [...] }
    """
    try:
        data = request.get_json()

        if not data or 'code' not in data:
            return jsonify({
                "success": False,
                "error": "缺少代码参数"
            }), 400

        code = data['code']
        defects_json = data.get('defects', '')

        # 如果没有提供缺陷报告，先让用户调用分析API
        if not defects_json:
            return jsonify({
                "success": False,
                "error": "缺少缺陷报告，请先调用 /api/analyze-code 进行分析"
            }), 400

        # 创建修复计划
        repair_plan_json = decision_manager.analyze(defects_json)

        # 执行修复
        fix_result_json = code_fixer.fix_code(repair_plan_json, defects_json)

        # 解析修复结果
        from schemas.fix_result import FixResult
        fix_result = FixResult.from_json(fix_result_json)

        return jsonify({
            "success": True,
            "fixed_code": fix_result.fixed_code,
            "original_code": fix_result.original_code,
            "strategy_used": fix_result.strategy_used,
            "changes_made": fix_result.changes_made,
            "confidence": fix_result.confidence
        })

    except Exception as e:
        logger.error(f"代码修复API错误: {str(e)}")
        return jsonify({
            "success": False,
            "error": f"修复失败: {str(e)}"
        }), 500


@api_blueprint.route('/analyze-code', methods=['POST'])
def analyze_code():
    """
    代码分析API
    接收: { "code": "代码内容" }
    返回: { "success": true, "defects": [...] }
    """
    try:
        data = request.get_json()
        code = data.get('code', '')

        if not code.strip():
            return jsonify({
                "success": False,
                "error": "代码不能为空"
            }), 400

        # 使用AI优先的分析服务
        result = analysis_service.analyze_code(code, file_path=data.get('file_path', 'input_code.py'))

        return jsonify({
            "success": True,
            **result
        })

    except Exception as e:
        logger.error(f"代码分析API错误: {str(e)}")
        return jsonify({
            "success": False,
            "error": f"分析失败: {str(e)}"
        }), 500


@api_blueprint.route('/generate-plan', methods=['POST'])
def generate_repair_plan():
    """
    生成修复计划API
    接收: { "defects": "缺陷报告JSON" }
    返回: { "success": true, "repair_plan": {...} }
    """
    try:
        data = request.get_json()
        defects_json = data.get('defects', '')

        if not defects_json:
            return jsonify({
                "success": False,
                "error": "缺少缺陷报告"
            }), 400

        # 使用你的DecisionManager生成修复计划
        repair_plan_json = decision_manager.analyze(defects_json)
        repair_plan = RepairPlan.from_json(repair_plan_json)

        return jsonify({
            "success": True,
            "repair_plan": {
                "total_tasks": repair_plan.total_tasks,
                "tasks": [
                    {
                        "file_path": task.file_path,
                        "strategy": task.strategy,
                        "priority": task.priority
                    }
                    for task in repair_plan.tasks
                ]
            }
        })

    except Exception as e:
        logger.error(f"生成修复计划API错误: {str(e)}")
        return jsonify({
            "success": False,
            "error": f"生成修复计划失败: {str(e)}"
        }), 500


@api_blueprint.route('/upload-files', methods=['POST'])
def upload_files():
    """
    多文件上传API（支持文件夹上传）
    接收: multipart/form-data 格式的文件上传
    返回: { "success": true, "files": [{"name": "文件名", "content": "文件内容"}] }
    """
    try:
        # 定义允许的文件扩展名
        ALLOWED_EXTENSIONS = {'.py', '.js', '.java', '.cpp', '.txt'}

        # 检查是否有文件
        if 'files' not in request.files:
            return jsonify({
                "success": False,
                "error": "没有文件上传"
            }), 400

        files = request.files.getlist('files')
        uploaded_files = []

        for file in files:
            if file and file.filename:
                # 安全处理文件名
                filename = secure_filename(file.filename)

                # 检查文件扩展名
                file_ext = os.path.splitext(filename)[1].lower()
                if file_ext not in ALLOWED_EXTENSIONS:
                    return jsonify({
                        "success": False,
                        "error": f"无效的文件类型，只允许 {', '.join(ALLOWED_EXTENSIONS)} 文件"
                    }), 400

                # 读取文件内容
                content = file.read().decode('utf-8')
                uploaded_files.append({
                    "name": filename,
                    "content": content
                })

        if not uploaded_files:
            return jsonify({
                "success": False,
                "error": "未成功上传任何文件"
            }), 400

        return jsonify({
            "success": True,
            "message": f"成功上传 {len(uploaded_files)} 个文件",
            "files": uploaded_files
        })

    except UnicodeDecodeError:
        logger.error("文件编码错误，只支持UTF-8编码的文本文件")
        return jsonify({
            "success": False,
            "error": "文件编码错误，只支持UTF-8编码的文本文件"
        }), 400
    except Exception as e:
        logger.error(f"文件上传API错误: {str(e)}")
        return jsonify({
            "success": False,
            "error": f"文件上传失败: {str(e)}"
        }), 500


@api_blueprint.route('/analyze-project', methods=['POST'])
def analyze_project():
    """
    分析整个项目（多个文件）
    接收: { "files": [{"name": "文件名", "content": "文件内容"}] }
    返回: { "success": true, "defect_report": {...} }
    """
    try:
        data = request.get_json()
        files = data.get('files', [])

        if not files:
            return jsonify({
                "success": False,
                "error": "没有文件需要分析"
            }), 400

        # 为所有文件生成统一的缺陷报告
        file_defects_list = []
        total_defects = 0

        for file_info in files:
            filename = file_info.get('name', 'unknown.py')
            content = file_info.get('content', '')

            if content.strip():
                # 分析单个文件
                result = analysis_service.analyze_code(content, file_path=filename)
                defects = result.get('defects', [])
                total_defects += len(defects)

                # 创建文件缺陷列表
                normalized_defects = []
                for d in defects:
                    normalized_defects.append(Defect(
                        type=d.get('type', 'code_smell'),
                        message=d.get('message', ''),
                        line_number=int(d.get('line_number', 1)),
                        severity=d.get('severity', 'MEDIUM'),
                        tool=d.get('tool', 'llm'),
                        confidence=float(d.get('confidence', 0.7))
                    ))

                file_defects = FileDefects(file_path=filename, defects=normalized_defects)
                file_defects_list.append(file_defects)

        # 创建完整的缺陷报告
        defect_report = DefectReport(
            files=file_defects_list,
            summary={"total_defects": total_defects, "total_files": len(file_defects_list)}
        )

        return jsonify({
            "success": True,
            "defect_report": defect_report.to_dict(),
            "summary": {
                "total_files_analyzed": len(files),
                "files_with_defects": len(file_defects_list),
                "total_defects": total_defects
            }
        })

    except Exception as e:
        logger.error(f"项目分析API错误: {str(e)}")
        return jsonify({
            "success": False,
            "error": f"项目分析失败: {str(e)}"
        }), 500


@api_blueprint.route('/batch-fix', methods=['POST'])
def batch_fix():
    """
    批量修复项目文件
    接收: { "files": [{"name": "文件名", "content": "文件内容"}], "defect_report": {...} }
    返回: { "success": true, "fixed_files": [{"name": "文件名", "content": "修复后内容", "changes": [...] }] }
    """
    try:
        data = request.get_json()
        files = data.get('files', [])
        defect_report_dict = data.get('defect_report', {})

        if not files:
            return jsonify({
                "success": False,
                "error": "没有文件需要修复"
            }), 400

        if not defect_report_dict:
            return jsonify({
                "success": False,
                "error": "缺少缺陷报告"
            }), 400

        # 转换缺陷报告
        defect_report = DefectReport.from_dict(defect_report_dict)

        # 生成修复计划
        repair_plan_json = decision_manager.analyze(defect_report.to_json())

        # 处理每个文件的修复
        fixed_files = []
        files_dict = {file_info['name']: file_info['content'] for file_info in files}

        for file_defects in defect_report.files:
            if file_defects.file_path in files_dict:
                # 为单个文件创建临时的缺陷报告
                single_file_report = DefectReport(
                    files=[file_defects],
                    summary={"total_defects": len(file_defects.defects)}
                )

                # 执行修复
                fix_result_json = code_fixer.fix_code(repair_plan_json, single_file_report.to_json())
                from schemas.fix_result import FixResult
                fix_result = FixResult.from_json(fix_result_json)

                fixed_files.append({
                    "name": file_defects.file_path,
                    "original_content": files_dict[file_defects.file_path],
                    "fixed_content": fix_result.fixed_code,
                    "changes_made": fix_result.changes_made,
                    "strategy_used": fix_result.strategy_used,
                    "confidence": fix_result.confidence,
                    "defects_count": len(file_defects.defects)
                })

        return jsonify({
            "success": True,
            "message": f"成功处理 {len(fixed_files)} 个文件",
            "fixed_files": fixed_files,
            "summary": {
                "total_files_processed": len(files),
                "fixed_files_count": len(fixed_files),
                "total_defects": sum(file['defects_count'] for file in fixed_files)
            }
        })

    except Exception as e:
        logger.error(f"批量修复API错误: {str(e)}")
        return jsonify({
            "success": False,
            "error": f"批量修复失败: {str(e)}"
        }), 500


@api_blueprint.route('/run-pipeline', methods=['POST'])
def run_pipeline():
    """
    触发后端异步全流程：分析 -> 检测 -> 修复 -> 质量评估
    接收可选参数：{ "use_deepseek": true }
    返回 { "success": true, "task_id": "..." }
    """
    try:
        data = request.get_json() or {}
        options = data.get('options', {}) if isinstance(data, dict) else {}
        task_id = pipeline_service.start_pipeline(options)
        return jsonify({"success": True, "task_id": task_id})
    except Exception as e:
        logger.error(f"run-pipeline error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@api_blueprint.route('/task-status/<task_id>', methods=['GET'])
def task_status(task_id: str):
    try:
        status = pipeline_service.get_status(task_id)
        if not status:
            return jsonify({"success": False, "error": "task not found"}), 404
        # Normalize artifacts into downloadable URLs for frontend
        artifacts = status.get('artifacts', {}) or {}
        artifact_list = []
        for key, val in artifacts.items():
            # val is expected to be a filename in the task output dir
            artifact_list.append({
                'name': val,
                'type': key,
                'url': f"/api/artifact/{task_id}/{val}"
            })
        # expose a minimal safe status to frontend
        safe_status = {
            'id': status.get('id'),
            'status': status.get('status'),
            'stage': status.get('stage'),
            'progress': status.get('progress'),
            'artifacts': artifact_list,
            'started_at': status.get('started_at'),
            'finished_at': status.get('finished_at'),
            'last_message': status.get('last_message'),
            'log_tail': status.get('log_tail', '')
        }
        return jsonify({"success": True, "status": safe_status})
    except Exception as e:
        logger.error(f"task-status error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@api_blueprint.route('/artifact/<task_id>/<path:name>', methods=['GET'])
def get_artifact(task_id: str, name: str):
    try:
        status = pipeline_service.get_status(task_id)
        if not status:
            return jsonify({"success": False, "error": "task not found"}), 404
        out_dir = status.get('output_dir')
        if not out_dir:
            return jsonify({"success": False, "error": "no output dir"}), 404
        file_path = os.path.join(out_dir, name)
        if not os.path.isfile(file_path):
            return jsonify({"success": False, "error": "artifact not found"}), 404
        # use flask send_file to stream the file
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        logger.error(f"get_artifact error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


def _defects_to_report_json(defects: list, file_path: str) -> str:
    """将 defects 列表转换为 DefectReport JSON（用于修复端到端流程）"""
    from schemas.defect_report import DefectReport, FileDefects, Defect

    normalized = []
    for d in defects:
        normalized.append(Defect(
            type=d.get('type', 'code_smell'),
            message=d.get('message', ''),
            line_number=int(d.get('line_number', 1)),
            severity=d.get('severity', 'MEDIUM'),
            tool=d.get('tool', 'llm'),
            confidence=float(d.get('confidence', 0.7))
        ))

    file_defects = FileDefects(file_path=file_path, defects=normalized)
    report = DefectReport(files=[file_defects], summary={"total_defects": len(normalized)})
    return report.to_json()


def analyze_code_simple(code: str) -> list:
    """保留兼容函数（不再在路由中使用）"""
    return []


def find_line_number(code: str, pattern: str) -> int:
    """查找模式在代码中的行号"""
    lines = code.split('\n')
    for i, line in enumerate(lines, 1):
        if pattern in line:
            return i
    return 1