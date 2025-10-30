# 修复 FixStatusTracker.py 中的导入问题
import datetime
import json
import os
import logging

# 添加日志器
logger = logging.getLogger(__name__)

# 如果无法导入 schemas，使用本地定义
try:
    from schemas.defect_report import Defect
except ImportError:
    # 本地定义简单的 Defect 类
    class Defect:
        def __init__(self, type, message, line_number, severity):
            self.type = type
            self.message = message
            self.line_number = line_number
            self.severity = severity


class FixStatusTracker:
    """修复状态跟踪器"""

    def __init__(self, status_file="fix_status.json"):
        self.status_file = status_file
        self.status_data = self._load_status()
        # 新增：当前会话的修复记录，避免跨会话污染
        self.current_session_fixes = set()

    def is_defect_fixed(self, file_path: str, defect: Defect) -> bool:
        """检查缺陷是否已修复 - 修复版本"""
        # 首先检查当前会话
        session_key = f"{file_path}:{defect.line_number}:{hash(defect.message)}"
        if session_key in self.current_session_fixes:
            return True

        # 然后检查持久化状态
        defect_key = f"{file_path}:{defect.line_number}:{self._normalize_message(defect.message)}"

        # 如果状态文件中存在记录，进一步验证文件内容
        if defect_key in self.status_data.get("fixed_defects", {}):
            # 验证文件是否仍然存在且内容匹配
            if not self._validate_fix_still_valid(file_path, defect, defect_key):
                # 如果修复无效，移除记录
                del self.status_data["fixed_defects"][defect_key]
                self.save_status()
                return False
            return True

        return False

    def _validate_fix_still_valid(self, file_path: str, defect: Defect, defect_key: str) -> bool:
        """验证修复是否仍然有效"""
        try:
            if not os.path.exists(file_path):
                return False

            # 获取保存的修复哈希
            saved_fix = self.status_data["fixed_defects"][defect_key]
            saved_hash = saved_fix.get("fix_hash", "")

            # 读取当前文件内容
            with open(file_path, 'r', encoding='utf-8') as f:
                current_code = f.read()

            # 计算当前哈希
            current_hash = self.get_fix_hash(current_code)

            # 如果哈希不匹配，说明文件已被修改
            return current_hash == saved_hash

        except Exception:
            return False

    def _normalize_message(self, message: str) -> str:
        """标准化缺陷消息，用于比较"""
        # 移除可能变化的部分，如行号、路径等
        import re
        # 移除可能的文件路径和行号引用
        normalized = re.sub(r'[a-zA-Z]:\\[^ ]+', '[PATH]', message)
        normalized = re.sub(r'/[\w/.-]+', '[PATH]', normalized)
        normalized = re.sub(r'line \d+', 'line [LINE]', normalized)
        return normalized[:100]  # 只取前100个字符避免过长

    def mark_defect_fixed(self, file_path: str, defect: Defect, fix_hash: str):
        """标记缺陷已修复 - 修复版本"""
        # 添加到当前会话
        session_key = f"{file_path}:{defect.line_number}:{hash(defect.message)}"
        self.current_session_fixes.add(session_key)

        # 添加到持久化状态
        defect_key = f"{file_path}:{defect.line_number}:{self._normalize_message(defect.message)}"

        self.status_data.setdefault("fixed_defects", {})[defect_key] = {
            "fix_hash": fix_hash,
            "fix_time": datetime.datetime.now().isoformat(),
            "defect_info": {
                "type": defect.type,
                "message": self._normalize_message(defect.message),
                "line_number": defect.line_number,
                "severity": defect.severity
            },
            "file_path": file_path
        }
        self.save_status()

    def _load_status(self):
        """加载修复状态"""
        try:
            if os.path.exists(self.status_file):
                with open(self.status_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"加载修复状态失败: {str(e)}")
        return {"fixed_defects": {}, "file_versions": {}}

    def save_status(self):
        """保存修复状态"""
        try:
            with open(self.status_file, 'w', encoding='utf-8') as f:
                json.dump(self.status_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存修复状态失败: {str(e)}")



    def get_fix_hash(self, code: str) -> str:
        """生成代码哈希用于跟踪修改"""
        import hashlib
        clean_code = self._remove_comments_and_whitespace(code)
        return hashlib.md5(clean_code.encode()).hexdigest()

    def _remove_comments_and_whitespace(self, code: str) -> str:
        """移除注释和空白字符"""
        import re
        try:
            # 移除单行注释
            code = re.sub(r'#.*$', '', code, flags=re.MULTILINE)
            # 移除多行注释
            code = re.sub(r'\"\"\"[\s\S]*?\"\"\"', '', code)
            code = re.sub(r"\'\'\'[\s\S]*?\'\'\'", '', code)
            # 移除空白字符
            code = re.sub(r'\s+', ' ', code)
            return code.strip()
        except:
            return code