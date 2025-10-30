from datetime import datetime
import logging
import os
import re
from typing import Dict, List, Optional, Tuple

from schemas.defect_report import DefectReport, FileDefects, Defect
from schemas.fix_result import FixResult
from schemas.repair_plan import RepairTask, RepairPlan
from utils.file_utils import read_file
from utils.ai_fixer import ai_fixer  # 导入AI修复引擎


logger = logging.getLogger(__name__)


class CodeFixerAgent:
    """
        代码修复代理 - 核心修复引擎
        ===========================

        功能概述:
        ---------
        1. 支持多种修复策略（规则修复 + AI修复）
        2. 修复结果跟踪和报告生成
        3. 修复质量验证
        4. 多轮修复机制

        模块结构:
        ---------
        - 核心修复流程控制
        - 安全漏洞修复模块
        - 语法错误修复模块
        - 逻辑错误修复模块
        - AI修复集成模块
        - 修复验证模块
        - 报告生成模块
        """
    def __init__(self):
        # ==================== 修复策略注册表 ====================
        # 注意：后续扩展新语言时，需要在这里注册新的修复策略
        # 策略命名规范: {问题类型}_{修复动作}_{目标}
        self.strategies = {
             # ========== 安全漏洞修复策略 ==========
            "replace_eval_with_ast_literal_eval": self._replace_eval_strategy,           # eval安全替换
            "fix_pickle_security": self._fix_pickle_security_strategy,                   # pickle反序列化安全
            "fix_hardcoded_secrets": self._fix_hardcoded_secrets_strategy,               # 硬编码密码
            "fix_sql_injection": self._fix_sql_injection_strategy,                       # SQL注入
            "fix_command_injection": self._fix_command_injection_strategy,               # 命令注入

            # ========== 语法错误修复策略 ==========
            "fix_syntax_error": self._fix_syntax_error_strategy,                         # 通用语法错误
            "fix_indentation": self._fix_indentation_strategy,                           # 缩进错误

            # ========== 逻辑错误修复策略 ==========
            "add_null_check": self._add_null_check_strategy,                             # 空值检查
            "add_type_hint": self._add_type_hint_strategy,                               # 类型提示

            # ========== AI修复策略 ==========
            "ai_automatic_fix": self._ai_automatic_fix_strategy,                         # AI自动修复

            # ========== C++专用修复策略 ==========
            "fix_cpp_include_issues": self._fix_cpp_include_issues_strategy,
            "fix_cpp_memory_leak": self._fix_cpp_memory_leak_strategy,
            "fix_cpp_syntax": self._fix_cpp_syntax_strategy,
            "fix_cpp_performance": self._fix_cpp_performance_strategy,
            "fix_cpp_code_smell": self._fix_cpp_code_smell_strategy,
            "fix_cpp_qt_specific": self._fix_cpp_qt_specific_strategy,

        }
        # ==================== API调用控制 ====================
        self.api_call_count = 0
        self.max_api_calls = 20  # 限制总API调用次数，避免费用过高

        # ==================== 修复结果存储 ====================
        # 用于生成详细报告和后续分析
        self.fix_results = []
        self.report_dir = "test_results"

    # ============================================================================
    # 🎯 核心修复流程控制模块
    # ============================================================================
    def fix_code(self, repair_plan_json: str, defect_report_json: str) -> str:
        """
        🚀 主修复入口方法 - 公开接口
        ---------------------------
        功能: 根据修复计划执行代码修复
        输入:
            - repair_plan_json: 修复计划JSON字符串
            - defect_report_json: 缺陷报告JSON字符串
        输出: 修复结果JSON字符串
        """
        try:
            # 不清空之前的结果，而是累积所有修复结果
            # self.fix_results = []  # 注释掉这行，让结果累积

            # 解析输入数据
            repair_plan = RepairPlan.from_json(repair_plan_json)
            defect_report = DefectReport.from_json(defect_report_json)

            fix_results = []
            for task in repair_plan.tasks:
                fix_result = self._execute_repair_task(task, defect_report)
                if fix_result:
                    fix_results.append(fix_result)

            # 移除自动报告生成逻辑，由主系统统一生成
            # if self.fix_results:
            #     report_path = self._generate_detailed_fix_report()
            #     logger.info(f"详细修复报告已生成: {report_path}")
            # else:
            #     logger.info("无修复结果可生成报告")

            # 报告生成已移到主系统统一处理
            if fix_results:
                return fix_results[0].to_json()
            else:
                return FixResult(
                    file_path="",
                    original_code="",
                    fixed_code="",
                    strategy_used="no_fix_applied",
                    changes_made=["无修复任务或所有修复都失败了"],
                    confidence=0.0
                ).to_json()

        except Exception as e:
            logger.error(f"修复代码时发生错误: {str(e)}")
            import traceback
            traceback.print_exc()

            return FixResult(
                file_path="",
                original_code="",
                fixed_code="",
                strategy_used="error",
                changes_made=[f"修复失败: {str(e)}"],
                confidence=0.0
            ).to_json()

    def _execute_repair_task(self, task: RepairTask, defect_report: DefectReport) -> Optional[FixResult]:
        """
        🔧 执行单个修复任务 - 内部核心方法
        --------------------------------
        功能: 执行具体的修复任务并记录结果 增强版本，支持多语言
        流程:
          1. 定位缺陷信息
          2. 读取原始代码
          3. 执行策略修复
          4. 验证修复结果
          5. 记录修复详情
        """
        try:
            # 定位缺陷信息
            file_defects = self._find_file_defects(task.file_path, defect_report)
            if not file_defects or not file_defects.defects:
                logger.warning(f"未找到文件缺陷或缺陷列表为空: {task.file_path}")
                return None

            # 获取具体的缺陷
            if task.defect_index >= len(file_defects.defects):
                logger.warning(f"缺陷索引超出范围: {task.defect_index}")
                return None

            defect = file_defects.defects[task.defect_index]

            # 读取原始代码
            try:
                original_code = read_file(task.file_path)
            except Exception as e:
                logger.error(f"读取文件失败: {task.file_path}, 错误: {str(e)}")
                return None

            # 检测代码语言 - 使用增强版本
            detected_language = self._detect_language(task.file_path, original_code)
            logger.info(f"检测到语言: {detected_language}, 文件: {task.file_path}")

            # 记录修复信息，包含语言信息
            logger.info(
                f"执行修复任务: 文件={task.file_path}, 行号={defect.line_number}, "
                f"策略={task.strategy}, 语言={detected_language}, 缺陷类型={defect.type}"
            )

            # 提取原始代码片段
            original_snippet = self._extract_code_snippet(original_code, defect.line_number)

            # 执行修复策略，传递语言信息
            strategy_func = self.strategies.get(task.strategy)
            if not strategy_func:
                logger.warning(f"未知的修复策略: {task.strategy}")
                fixed_code, changes = original_code, [f"未知策略: {task.strategy}"]
                success = False
            else:
                # 调用修复策略，传递语言信息
                fixed_code, changes = strategy_func(original_code, defect, task.context, detected_language)

                # 修复成功判断逻辑 - 根据语言调整标准
                success = self._evaluate_repair_success(original_code, fixed_code, changes, detected_language)

            # 提取修复后代码片段
            fixed_snippet = self._extract_code_snippet(fixed_code, defect.line_number)

            # 记录修复结果
            result_record = {
                'file_path': task.file_path,
                'defect_type': defect.type,
                'defect_message': defect.message,
                'line_number': defect.line_number,
                'strategy': task.strategy,
                'language': detected_language,  # 添加语言信息
                'success': success,
                'confidence': 0.9 if success else 0.1,
                'changes_made': changes,
                'original_code_snippet': original_snippet,
                'fixed_code_snippet': fixed_snippet if fixed_code != original_code else "无变化",
                'timestamp': datetime.now().isoformat()
            }
            self.fix_results.append(result_record)

            logger.info(f"修复完成，成功: {success}, 语言: {detected_language}, 变更数量: {len(changes)}")

            return FixResult(
                file_path=task.file_path,
                original_code=original_code,
                fixed_code=fixed_code,
                strategy_used=task.strategy,
                changes_made=changes,
                confidence=0.9 if success else 0.1
            )

        except Exception as e:
            logger.error(f"执行修复任务时发生错误: {str(e)}")

            # 记录失败结果 - 确保即使异常也记录
            result_record = {
                'file_path': task.file_path if 'task' in locals() else 'unknown',
                'defect_type': defect.type if 'defect' in locals() else 'unknown',
                'defect_message': defect.message if 'defect' in locals() else str(e),
                'line_number': defect.line_number if 'defect' in locals() else 0,
                'strategy': task.strategy if 'task' in locals() else 'unknown',
                'success': False,
                'confidence': 0.0,
                'changes_made': [f"执行错误: {str(e)}"],
                'original_code_snippet': '',
                'fixed_code_snippet': '',
                'timestamp': datetime.now().isoformat()
            }
            self.fix_results.append(result_record)

            return None

    def _detect_language(self, file_path: str, code: str) -> str:
        """检测代码语言 - 增强版本"""
        # 优先通过文件扩展名检测
        cpp_extensions = {'.cpp', '.cc', '.cxx', '.c++', '.h', '.hpp', '.hxx', '.hh'}
        python_extensions = {'.py', '.pyw'}

        file_ext = '.' + file_path.split('.')[-1].lower() if '.' in file_path else ''

        if file_ext in cpp_extensions:
            return "cpp"
        elif file_ext in python_extensions:
            return "python"

        # 通过代码内容检测（备用方案）
        cpp_keywords = [
            '#include', 'using namespace', 'class ', 'struct ',
            'public:', 'private:', 'protected:', 'virtual ', 'template<',
            'cout <<', 'endl;', '->', '::', 'new ', 'delete '
        ]
        python_keywords = [
            'def ', 'import ', 'from ', 'class ', 'print(', 'lambda ',
            'if __name__', 'self.', 'super()'
        ]

        cpp_count = sum(1 for keyword in cpp_keywords if keyword in code)
        python_count = sum(1 for keyword in python_keywords if keyword in code)

        if cpp_count > python_count:
            return "cpp"
        elif python_count > cpp_count:
            return "python"
        else:
            # 默认根据文件路径判断
            if any(ext in file_path for ext in cpp_extensions):
                return "cpp"
            else:
                return "python"

    # ============================================================================
    # 🔒 安全漏洞修复模块
    # ============================================================================

    def _replace_eval_strategy(self, code: str, defect: Defect, context: Dict, language: str = "python") -> Tuple[str, List[str]]:
        """
        🔒 安全修复: eval替换策略
        ----------------------
        静态分析方法: 正则匹配eval调用模式
        动态验证: 检查修复后是否还有eval残留
        语言相关: Python特定，其他语言需重写
        """
        if language != "python":
            return code, [f"eval替换策略仅支持Python，当前语言: {language}"]

        changes = []

        print(f"🔍 开始eval替换策略: 行号={defect.line_number}")
        print(f"原始代码:\n{code}")

        # 分割代码行
        lines = code.split('\n')

        # 检查是否在指定行有eval调用
        if 0 < defect.line_number <= len(lines):
            line_index = defect.line_number - 1
            original_line = lines[line_index]

            print(f"目标行 {defect.line_number}: '{original_line}'")

            # 检查这一行是否有eval调用
            if 'eval(' in original_line:
                print("找到eval调用，开始处理...")

                # 首先确保导入了ast
                ast_imported = False
                ast_import_line = -1

                # 检查是否已经导入了ast
                for i, line in enumerate(lines):
                    if 'import ast' in line:
                        ast_imported = True
                        ast_import_line = i
                        break

                if not ast_imported:
                    print("需要添加import ast")
                    # 找到合适的导入位置
                    import_inserted = False
                    for i, line in enumerate(lines):
                        if line.strip().startswith('import ') or line.strip().startswith('from '):
                            # 在现有导入后添加
                            lines.insert(i + 1, 'import ast')
                            ast_import_line = i + 1
                            import_inserted = True
                            changes.append("添加了 import ast")
                            ast_imported = True
                            print(f"在导入语句后添加import ast (第{ast_import_line + 1}行)")
                            break

                    if not import_inserted:
                        # 在文件开头添加
                        lines.insert(0, 'import ast')
                        ast_import_line = 0
                        changes.append("添加了 import ast")
                        ast_imported = True
                        print("在文件开头添加import ast")
                else:
                    print(f"import ast已存在 (第{ast_import_line + 1}行)")
                    ast_imported = True

                # 替换当前行的eval调用
                fixed_line = original_line.replace('eval(', 'ast.literal_eval(')
                lines[line_index] = fixed_line
                changes.append(f"将第{defect.line_number}行的eval()替换为ast.literal_eval()")
                print(f"替换行: '{original_line}' -> '{fixed_line}'")

                fixed_code = '\n'.join(lines)

                # 验证修复 - 检查是否还有eval调用（除了import语句）
                remaining_evals = 0
                for i, line in enumerate(lines):
                    if i != ast_import_line and 'eval(' in line and not line.strip().startswith('#'):
                        remaining_evals += 1
                        print(f"发现剩余的eval调用在第{i + 1}行: {line}")

                if remaining_evals > 0:
                    changes.append(f"警告：修复后仍然存在{remaining_evals}个eval调用")
                    print(f"⚠️ 警告：修复后代码中仍然存在{remaining_evals}个eval调用")

                    # 如果还有eval调用，直接使用AI修复整个文件
                    print("使用AI修复整个文件...")
                    ai_result = ai_fixer.fix_with_ai(code, "将所有eval调用替换为ast.literal_eval，并确保导入ast模块", "",
                                                     "python")
                    if ai_result["success"]:
                        changes.append("使用AI修复所有eval调用")
                        return ai_result["fixed_code"], changes

                print(f"修复后代码:\n{fixed_code}")
                return fixed_code, changes
            else:
                changes.append(f"第{defect.line_number}行没有找到eval调用: {original_line}")
                print(f"第{defect.line_number}行没有eval调用: '{original_line}'")
        else:
            changes.append(f"行号{defect.line_number}超出范围（总行数: {len(lines)}）")
            print(f"行号{defect.line_number}超出范围（总行数: {len(lines)}）")

        return code, changes

    def _fix_pickle_security_strategy(self, code: str, defect: Defect, context: Dict, language: str = "python") -> Tuple[str, List[str]]:
        """
        🔒 安全修复: pickle反序列化安全
        ----------------------------
        静态分析: 检测pickle导入和使用
        修复方案: 添加安全警告或替换序列化方式
        """
        if language != "python":
            return code, [f"pickle安全修复仅支持Python，当前语言: {language}"]

        changes = []

        # 使用AI修复pickle安全问题
        ai_prompt = "修复pickle反序列化安全问题，添加安全警告或使用更安全的序列化方式"
        ai_result = ai_fixer.fix_with_ai(code, ai_prompt, "", "python")

        if ai_result["success"]:
            changes.append("使用AI修复pickle反序列化安全问题")
            return ai_result["fixed_code"], changes
        else:
            # 基本修复：添加警告注释
            lines = code.split('\n')
            fixed_code = code
            if "import pickle" in code and not any("警告" in line or "warning" in line.lower() for line in lines):
                # 在import语句后添加警告
                for i, line in enumerate(lines):
                    if "import pickle" in line:
                        warning_line = "# 警告: pickle反序列化可能存在安全风险，建议使用更安全的序列化格式如JSON"
                        lines.insert(i + 1, warning_line)
                        changes.append("添加pickle安全警告")
                        fixed_code = '\n'.join(lines)
                        break

            if not changes:
                changes.append("无法修复pickle安全问题")

            return fixed_code, changes

    def _fix_hardcoded_secrets_strategy(self, code: str, defect: Defect, context: Dict, language: str = "python") -> Tuple[str, List[str]]:
        """
        🔒 安全修复: 硬编码密码检测和修复
        ------------------------------
        静态分析: 正则匹配密码模式
        动态修复: 替换为环境变量
        语言相关: Python特定模式
        """
        if language != "python":
            return code, [f"硬编码密码修复策略仅支持Python，当前语言: {language}"]

        changes = []
        lines = code.split('\n')

        print(f"🔍 开始硬编码密码修复策略: 行号={defect.line_number}")
        print(f"缺陷描述: {defect.message}")

        if 0 < defect.line_number <= len(lines):
            line_index = defect.line_number - 1
            target_line = lines[line_index]

            print(f"目标行内容: '{target_line}'")

            # 更精确的硬编码密码模式匹配
            secret_patterns = [
                (r'(\w+)\s*=\s*["\']([^"\']*password[^"\']*)["\']', 'password'),
                (r'(\w+)\s*=\s*["\']([^"\']*secret[^"\']*)["\']', 'secret'),
                (r'(\w+)\s*=\s*["\']([^"\']*key[^"\']*)["\']', 'key'),
                (r'(\w+)\s*=\s*["\']([^"\']*token[^"\']*)["\']', 'token'),
                (r'(\w+)\s*=\s*["\']([^"\']*credential[^"\']*)["\']', 'credential'),
            ]

            fixed_lines = lines.copy()  # 创建副本，避免修改原始列表
            secrets_found = []

            # 首先尝试精确修复目标行
            for pattern, secret_type in secret_patterns:
                match = re.search(pattern, target_line, re.IGNORECASE)
                if match:
                    var_name = match.group(1)
                    original_value = match.group(2)

                    print(f"找到硬编码{secret_type}: {var_name} = '{original_value}'")

                    # 生成环境变量名
                    env_var_name = f"{var_name.upper()}_SECRET"

                    # 替换为环境变量获取
                    new_line = re.sub(
                        r'=\s*["\'][^"\']*["\']',
                        f'= os.getenv("{env_var_name}", "{original_value}")',  # 提供默认值保持功能
                        target_line
                    )

                    if new_line != target_line:
                        fixed_lines[line_index] = new_line
                        secrets_found.append((var_name, secret_type, env_var_name))
                        changes.append(f"将硬编码{secret_type} '{var_name}' 替换为环境变量 {env_var_name}")
                        print(f"修复行: '{target_line}' -> '{new_line}'")
                        break

            # 如果找到硬编码密码，确保导入了os模块
            if secrets_found:
                has_os_import = any('import os' in line for line in fixed_lines)
                if not has_os_import:
                    # 在文件开头或导入部分添加import os
                    import_added = False
                    for i, line in enumerate(fixed_lines):
                        if line.strip().startswith('import ') or line.strip().startswith('from '):
                            # 在现有导入后添加
                            fixed_lines.insert(i + 1, 'import os')
                            import_added = True
                            changes.append("添加 import os")
                            print("添加了 import os")
                            break

                    if not import_added:
                        # 在文件开头添加
                        fixed_lines.insert(0, 'import os')
                        changes.append("在文件开头添加 import os")
                        print("在文件开头添加了 import os")

                fixed_code = '\n'.join(fixed_lines)

                # 验证修复：确保原始功能结构没有被破坏
                if 'AWS_OPTIONS' in code and 'AWS_OPTIONS' not in fixed_code:
                    print("⚠️ 警告：修复后丢失了AWS_OPTIONS字典，回退到AI修复")
                    # 如果关键结构被破坏，使用更保守的AI修复
                    return self._conservative_ai_fix(code, defect, "硬编码密码", changes)

                return fixed_code, changes

        # 如果规则修复失败，使用保守的AI修复
        print("规则修复未找到硬编码密码，尝试保守AI修复")
        return self._conservative_ai_fix(code, defect, "硬编码密码", changes)

    def _fix_sql_injection_strategy(self, code: str, defect: Defect, context: Dict, language: str = "python") -> Tuple[str, List[str]]:
        """
        🔒 安全修复: SQL注入防护
        ----------------------
        静态分析: 检测f-string SQL拼接
        动态修复: 参数化查询重构
        语言相关: Python的SQL模式
        """
        if language != "python":
            return code, [f"SQL注入修复仅支持Python，当前语言: {language}"]

        changes = []
        lines = code.split('\n')

        print(f"🔍 开始SQL注入修复策略: 行号={defect.line_number}")
        print(f"缺陷描述: {defect.message}")

        if 0 < defect.line_number <= len(lines):
            line_index = defect.line_number - 1
            target_line = lines[line_index]

            print(f"目标行内容: '{target_line}'")

            # 查找f-string的SQL查询
            sql_patterns = [
                r"f'[^']*\{[^}]+\}[^']*'",  # f'...{variable}...'
                r'f"[^"]*\{[^}]+\}[^"]*"',  # f"...{variable}..."
            ]

            fixed_lines = lines.copy()
            sql_injections_found = []

            for pattern in sql_patterns:
                if re.search(pattern, target_line):
                    print(f"发现f-string SQL查询: {target_line}")

                    # 分析SQL语句结构
                    if 'DELETE FROM' in target_line and 'WHERE' in target_line:
                        # 对于DELETE FROM {table} WHERE ... 模式
                        # 正确的修复：使用参数化查询，但表名通常不能参数化
                        # 所以需要验证表名是否安全，或者重构查询

                        # 提取表名变量
                        table_match = re.search(r"DELETE FROM\s*\{([^}]+)\}", target_line)
                        if table_match:
                            table_var = table_match.group(1)
                            # 验证表名变量是否是对象属性（相对安全）
                            if '.' in table_var or 'table_name' in table_var:
                                # 这种情况相对安全，因为表名来自代码内部而非用户输入
                                changes.append(f"第{defect.line_number}行的表名来自代码内部，SQL注入风险较低")
                                # 保持原代码，但添加安全注释
                                comment_line = f"    # 注意: 表名来自内部变量'{table_var}'，SQL注入风险较低"
                                if line_index > 0 and not fixed_lines[line_index - 1].strip().startswith('#'):
                                    fixed_lines.insert(line_index, comment_line)
                                    changes.append("添加安全注释")
                            else:
                                changes.append(f"表名变量'{table_var}'需要进一步安全检查")
                        else:
                            changes.append("无法提取表名变量")

                    elif 'SELECT' in target_line and 'WHERE' in target_line:
                        # 对于SELECT查询，检查是否有用户输入直接拼接
                        if any(char in target_line for char in ["'{", '"{']):
                            # 有用户输入直接拼接的情况
                            changes.append("检测到可能的用户输入拼接，需要重构为参数化查询")
                            # 使用AI进行精确修复
                            return self._conservative_sql_fix(code, defect, changes)
                        else:
                            # 主要是表名和列名的f-string，风险相对较低
                            changes.append("SQL查询主要涉及表名和列名，注入风险较低")

                    else:
                        # 其他类型的SQL语句，使用AI修复
                        return self._conservative_sql_fix(code, defect, changes)

                    sql_injections_found.append(target_line)
                    break

            if sql_injections_found:
                fixed_code = '\n'.join(fixed_lines)
                return fixed_code, changes
            else:
                print("未发现明显的SQL注入模式，尝试AI修复")
                return self._conservative_sql_fix(code, defect, changes)

        # 如果行号无效，使用AI修复
        return self._conservative_sql_fix(code, defect, changes)

    def _fix_command_injection_strategy(self, code: str, defect: Defect, context: Dict, language: str = "python") -> Tuple[str, List[str]]:
        """
        🔒 安全修复: 命令注入防护
        ----------------------
        静态分析: 检测不安全的命令执行函数
        动态修复: 替换为安全的subprocess调用
        """
        if language != "python":
            return code, [f"命令注入修复仅支持Python，当前语言: {language}"]

        changes = []

        # 查找不安全的命令执行
        unsafe_patterns = [
            r'os\.popen\(',
            r'os\.system\(',
            r'subprocess\.call\([^[]*shell=True',
            r'subprocess\.Popen\([^[]*shell=True',
        ]

        lines = code.split('\n')
        command_injection_found = False

        for i, line in enumerate(lines):
            for pattern in unsafe_patterns:
                if re.search(pattern, line):
                    command_injection_found = True
                    # 基本修复：将os.popen替换为subprocess.run
                    if 'os.popen' in line:
                        new_line = line.replace('os.popen', 'subprocess.run')
                        # 简单的参数调整
                        new_line = new_line.replace('.read()', ', capture_output=True, text=True).stdout')
                        if new_line != line:
                            lines[i] = new_line
                            changes.append(f"将第{i + 1}行的os.popen替换为subprocess.run")

        if command_injection_found:
            # 确保导入了subprocess
            has_subprocess_import = any('import subprocess' in line for line in lines)
            if not has_subprocess_import:
                import_added = False
                for j, line in enumerate(lines):
                    if line.strip().startswith('import ') or line.strip().startswith('from '):
                        lines.insert(j, 'import subprocess')
                        import_added = True
                        break
                if not import_added:
                    lines.insert(0, 'import subprocess')

            fixed_code = '\n'.join(lines)
        else:
            # 使用AI修复
            ai_prompt = "修复命令注入安全问题，使用安全的subprocess调用替代不安全的命令执行"
            ai_result = ai_fixer.fix_with_ai(code, ai_prompt, "", "python")
            if ai_result["success"]:
                changes.append("使用AI修复命令注入问题")
                return ai_result["fixed_code"], changes
            else:
                changes.append("未发现明显的命令注入问题")
                fixed_code = code

        return fixed_code, changes

    # ============================================================================
    # 📝 语法错误修复模块
    # ============================================================================

    def _fix_syntax_error_strategy(self, code: str, defect: Defect, context: Dict, language: str = "python") -> Tuple[str, List[str]]:
        """
        📝 语法修复: 通用语法错误修复
        ---------------------------
        静态分析: 语法模式匹配
        动态修复: 结构修正
        语言相关: 强Python相关
        """
        if language != "python":
            return code, [f"语法错误修复仅支持Python，当前语言: {language}"]

        changes = []
        lines = code.split('\n')
        fixed = False

        if 0 < defect.line_number <= len(lines):
            line_index = defect.line_number - 1
            problematic_line = lines[line_index]

            # 修复赋值操作符错误 (= 应该是 == 或 is)
            if '= None' in problematic_line and '==' not in problematic_line and 'if' in problematic_line:
                # 在条件语句中，= 应该是 == 或 is None
                if 'is' in problematic_line or 'is not' in problematic_line:
                    fixed_line = problematic_line.replace('= None', 'is None')
                else:
                    fixed_line = problematic_line.replace('= None', '== None')
                lines[line_index] = fixed_line
                changes.append(f"修复第{defect.line_number}行的语法错误：将=改为==")
                fixed = True

            # 修复缺少冒号
            elif re.search(r'^(?:\s*)(?:for|if|while|def|class|elif|else|try|except|finally)\b',
                           problematic_line) and not problematic_line.rstrip().endswith(':'):
                if not problematic_line.strip().endswith(':'):
                    fixed_line = problematic_line.rstrip() + ':'
                    lines[line_index] = fixed_line
                    changes.append(f"修复第{defect.line_number}行的语法错误：添加冒号")
                    fixed = True

        fixed_code = '\n'.join(lines)

        if not fixed:
            # 如果规则修复失败，尝试使用AI修复
            ai_result = ai_fixer.fix_with_ai(code, defect.message, "", "python")
            if ai_result["success"]:
                changes.append("使用AI修复语法错误")
                return ai_result["fixed_code"], changes
            changes.append("无法自动修复该语法错误")

        return fixed_code, changes

    def _fix_indentation_strategy(self, code: str, defect: Defect, context: Dict, language: str = "python") -> Tuple[str, List[str]]:
        """
        📝 语法修复: 缩进错误修复
        -----------------------
        静态分析: 缩进一致性检查
        动态修复: AI辅助缩进修正
        """
        if language != "python":
            return code, [f"缩进修复仅支持Python，当前语言: {language}"]

        # 使用AI修复缩进问题
        ai_result = ai_fixer.fix_with_ai(code, "缩进错误，请修复代码缩进", "", "python")
        if ai_result["success"]:
            return ai_result["fixed_code"], ["使用AI修复缩进错误"]
        return code, ["缩进修复失败"]

    # ============================================================================
    # 🧠 逻辑错误修复模块
    # ============================================================================

    def _add_null_check_strategy(self, code: str, defect: Defect, context: Dict, language: str = "python") -> Tuple[str, List[str]]:
        """
        🧠 逻辑修复: 空值检查添加
        -----------------------
        静态分析: 变量使用模式分析
        动态修复: 插入空值检查代码
        语言相关: Python的空值模式
        """
        if language != "python":
            return code, [f"空值检查策略仅支持Python，当前语言: {language}"]

        changes = []
        lines = code.split('\n')

        print(f"DEBUG: 开始空值检查策略，行号: {defect.line_number}, 消息: {defect.message}")

        if 0 < defect.line_number <= len(lines):
            line_index = defect.line_number - 1
            current_line = lines[line_index]

            # 分析缺陷消息来确定需要检查的变量
            target_variable = self._extract_variable_from_message(defect.message, current_line)

            print(f"DEBUG: 目标变量: '{target_variable}'")

            if target_variable:
                # 构建空值检查代码
                if self._is_function_parameter_context(lines, line_index):
                    # 函数参数检查 - 插入到函数体开始
                    check_code = f"    if {target_variable} is None:\n        raise ValueError(\"{target_variable} cannot be None\")"
                    func_body_start = self._find_function_body_start(lines, line_index)
                    if func_body_start != -1:
                        # 确保不会重复插入
                        existing_checks = [line for line in lines[func_body_start:func_body_start + 3]
                                           if f"if {target_variable} is None" in line]
                        if not existing_checks:
                            lines.insert(func_body_start, check_code)
                            changes.append(f"在函数开始处添加了{target_variable}的空值检查")
                        else:
                            changes.append(f"{target_variable}的空值检查已存在")
                    else:
                        changes.append("无法找到函数体开始位置")
                else:
                    # 普通变量检查 - 在当前行前插入
                    check_code = f"if {target_variable} is None:\n    raise ValueError(\"{target_variable} cannot be None\")"
                    # 检查是否已经存在相同的检查
                    existing_checks = [line for line in lines[max(0, line_index - 2):line_index]
                                       if f"if {target_variable} is None" in line]
                    if not existing_checks:
                        lines.insert(line_index, check_code)
                        changes.append(f"在第{line_index + 1}行前添加了{target_variable}的空值检查")
                    else:
                        changes.append(f"{target_variable}的空值检查已存在")
            else:
                changes.append("无法确定需要检查的变量")
                # 尝试使用AI
                ai_prompt = f"为以下代码添加适当的空值检查，处理缺陷: {defect.message}"
                ai_result = ai_fixer.fix_with_ai(code, ai_prompt, "", "python")
                if ai_result["success"]:
                    changes.append("使用AI添加空值检查")
                    return ai_result["fixed_code"], changes

        fixed_code = '\n'.join(lines)

        if not changes or "无法" in changes[0]:
            # 如果规则修复失败，尝试使用AI修复
            ai_prompt = f"为以下代码添加空值检查，处理缺陷: {defect.message}"
            ai_result = ai_fixer.fix_with_ai(code, ai_prompt, "", "python")
            if ai_result["success"]:
                changes.append("使用AI添加空值检查")
                return ai_result["fixed_code"], changes
            changes.append("无法添加空值检查")

        print(f"DEBUG: 修复完成，变更: {changes}")
        return fixed_code, changes

    def _add_type_hint_strategy(self, code: str, defect: Defect, context: Dict, language: str = "python") -> Tuple[str, List[str]]:
        """
        🧠 逻辑修复: 类型提示添加
        -----------------------
        静态分析: 函数签名分析
        动态修复: 添加类型注解
        """
        if language != "python":
            return code, [f"类型提示添加仅支持Python，当前语言: {language}"]
        # 使用AI添加类型提示
        ai_result = ai_fixer.fix_with_ai(code, "请为代码添加适当的类型提示", "", "python")
        if ai_result["success"]:
            return ai_result["fixed_code"], ["使用AI添加类型提示"]
        return code, ["类型提示添加失败"]

    # ============================================================================
    # 🤖 AI修复集成模块
    # ============================================================================

    def _ai_automatic_fix_strategy(self, code: str, defect: Defect, context: Dict, language: str = "python") -> Tuple[
        str, List[str]]:
        """AI修复: 自动修复策略 - 修复版本"""
        if not ai_fixer.is_available():
            logger.warning("AI修复引擎不可用，无法进行自动修复")
            return code, ["AI修复引擎不可用"]

        logger.info(f"使用AI自动修复策略处理缺陷: {defect.message}, 语言: {language}")

        # 记录API调用次数
        self.api_call_count += 1

        # 使用AI修复
        ai_result = ai_fixer.fix_with_ai(code, defect.message, "", language)

        if ai_result["success"]:
            fixed_code = ai_result["fixed_code"]

            # 使用简化的验证逻辑
            validation_result = self._validate_fix_quality(code, fixed_code, ["AI修复"], language)

            if validation_result["is_valid"]:
                changes = [f"使用AI自动修复({language}): {defect.message}"]
                logger.info(f"AI修复成功: {validation_result['message']}")
                return fixed_code, changes
            else:
                logger.warning(f"AI修复未通过验证: {validation_result['message']}")
                return code, [f"AI修复未通过验证: {validation_result['message']}"]
        else:
            logger.warning(f"AI修复失败: {ai_result['error_message']}")
            return code, [f"AI修复失败: {ai_result['error_message']}"]

    def _should_use_ai_fix(self, defect: Defect, task: RepairTask) -> bool:
        """
        🤖 AI修复: 使用条件判断
        ---------------------
        功能: 智能判断是否使用AI修复
        规则: 基于缺陷类型和API限制
        """
        # 如果已经达到API调用限制，不使用AI
        if self.api_call_count >= self.max_api_calls:
            logger.warning(f"达到API调用上限 {self.max_api_calls}，跳过AI修复")
            return False

        # 对于这些类型，优先使用规则修复
        message_lower = defect.message.lower()

        # 明确可以使用规则修复的情况
        rule_based_cases = [
            'eval' in message_lower,
            'sql' in message_lower and 'injection' in message_lower,
            'hardcoded' in message_lower,
            'password' in message_lower and 'hardcoded' in message_lower,
            'secret' in message_lower,
            'pickle' in message_lower,
            'indentation' in message_lower,
            'syntax' in message_lower and 'error' in message_lower,
        ]

        if any(rule_based_cases):
            return False

        # 对于逻辑错误，尝试使用规则修复
        if defect.type == "logic":
            logic_keywords = ['none', 'null', 'division', 'zero', 'index']
            if any(keyword in message_lower for keyword in logic_keywords):
                return False

        # 其他情况使用AI修复
        return True

    def _suggest_better_strategy(self, defect: Defect) -> str:
        """
        🤖 AI修复: 策略建议
        -----------------
        功能: 为缺陷推荐最佳修复策略
        规则: 基于缺陷消息内容分析
        """
        message_lower = defect.message.lower()

        # 安全相关缺陷
        if 'eval' in message_lower:
            return "replace_eval_with_ast_literal_eval"
        elif 'sql' in message_lower and 'injection' in message_lower:
            return "fix_sql_injection"
        elif 'hardcoded' in message_lower or 'password' in message_lower:
            return "fix_hardcoded_secrets"
        elif 'pickle' in message_lower:
            return "fix_pickle_security"

        # 语法错误
        elif 'syntax' in message_lower:
            if 'indentation' in message_lower:
                return "fix_indentation"
            else:
                return "fix_syntax_error"

        # 逻辑错误
        elif defect.type == "logic":
            if 'none' in message_lower or 'null' in message_lower:
                return "add_null_check"
            elif 'division' in message_lower or 'zero' in message_lower:
                return "add_null_check"

        # 默认使用AI修复
        return "ai_automatic_fix"

    # ============================================================================
    # 🔍 修复验证模块
    # ============================================================================

    def _validate_ai_fix(self, original_features: Dict, fixed_code: str, target_line: int) -> Dict:
        """
        🔍 修复验证: AI修复结果验证
        -------------------------
        功能: 验证AI修复后的代码质量
        验证维度:
          - 语法正确性
          - 关键结构保留
          - 功能完整性
        """
        validation_result = {
            "success": True,
            "reason": "",
            "details": []
        }

        # 1. 检查语法
        try:
            compile(fixed_code, '<string>', 'exec')
        except SyntaxError as e:
            validation_result["success"] = False
            validation_result["reason"] = f"语法错误: {str(e)}"
            return validation_result

        # 2. 检查关键特征是否保留
        fixed_lines = fixed_code.split('\n')
        original_line_count = original_features.get("line_count", 0)

        # 检查目标行附近的关键代码是否保留
        if target_line > 0 and target_line <= len(fixed_lines):
            target_content = original_features.get("target_line_content", "")
            if target_content and target_content not in fixed_code:
                validation_result["details"].append("目标行内容发生变化")

        # 3. 检查代码长度变化是否合理
        if len(fixed_code) < len(original_features.get("original_code", "")) * 0.3:
            validation_result["details"].append("修复后代码过短，可能丢失功能")
            validation_result["success"] = False
            validation_result["reason"] = "代码长度异常"

        # 4. 检查是否有明显的错误模式
        error_patterns = [
            "TODO",
            "FIXME",
            "raise NotImplementedError",
            "pass  #",
            "..."
        ]
        for pattern in error_patterns:
            if pattern in fixed_code:
                validation_result["details"].append(f"发现未完成标记: {pattern}")

        return validation_result

    def _extract_code_key_features(self, code: str, problem_line: int) -> Dict:
        """提取代码关键特征用于验证"""
        lines = code.split('\n')
        features = {
            'total_lines': len(lines),
            'function_defs': [],
            'imports': [],
            'problem_line_content': lines[problem_line - 1] if 0 < problem_line <= len(lines) else ""
        }

        for i, line in enumerate(lines):
            if line.strip().startswith('def '):
                features['function_defs'].append((i, line.strip()))
            elif line.strip().startswith('import ') or line.strip().startswith('from '):
                features['imports'].append(line.strip())

        return features

    def _validate_fix_preserves_structure(self, original_code: str, fixed_code: str, defect: Defect) -> bool:
        """
        🔍 修复验证: 结构保持检查
        -----------------------
        功能: 验证修复是否破坏了关键代码结构
        检查项: 函数定义、类定义、导入语句等
        """
        # 检查关键变量和结构是否被保留
        key_structures = ['AWS_OPTIONS', 'def ', 'class ', 'import ', 'from ']

        for structure in key_structures:
            if structure in original_code and structure not in fixed_code:
                print(f"⚠️ 验证失败：修复后丢失了关键结构 '{structure}'")
                return False

        # 检查代码长度变化是否合理
        if len(fixed_code) < len(original_code) * 0.7:
            print("⚠️ 验证失败：修复后代码过短")
            return False

        return True

    def _validate_sql_fix(self, original_code: str, fixed_code: str) -> bool:
        """
        🔍 修复验证: SQL修复质量
        ----------------------
        功能: 专门验证SQL相关的修复
        检查项: 语法正确性、功能完整性
        """
        # 检查修复后的代码是否包含明显的语法错误
        syntax_errors = [
            '%sself.',  # 错误的字符串格式化
            '%svariable',
            'f"SELECT * FROM %s'  # 混合使用f-string和%s
        ]

        for error_pattern in syntax_errors:
            if error_pattern in fixed_code:
                print(f"⚠️ 验证失败：修复后代码包含语法错误 '{error_pattern}'")
                return False

        # 检查关键SQL关键字是否被保留
        sql_keywords = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'FROM', 'WHERE']
        for keyword in sql_keywords:
            if keyword in original_code and keyword not in fixed_code:
                print(f"⚠️ 验证失败：修复后丢失了SQL关键字 '{keyword}'")
                return False

        # 检查代码长度变化是否合理
        if len(fixed_code) < len(original_code) * 0.5:
            print("⚠️ 验证失败：修复后代码过短")
            return False

        return True

    def _validate_fix_quality(self, original_code: str, fixed_code: str, changes: List[str], language: str) -> Dict:
        """修复质量验证 - 针对C++优化版本"""
        # 基本检查
        if fixed_code == original_code:
            return {"is_valid": False, "message": "代码无变化"}

        if len(fixed_code.strip()) < 10:
            return {"is_valid": False, "message": "修复后代码过短"}

        # C++特定验证 - 放宽标准
        if language == "cpp":
            # C++允许包含error/exception等关键词（可能是合法的错误处理）
            if "error" in fixed_code.lower() and "exception" in fixed_code.lower():
                # 检查是否是合法的错误处理代码
                error_patterns = [
                    "try", "catch", "throw", "exception",
                    "qdebug", "qcritical", "qwarning"
                ]
                if any(pattern in fixed_code.lower() for pattern in error_patterns):
                    # 这是合法的错误处理，不是真正的错误
                    pass
                else:
                    return {"is_valid": False, "message": "修复后代码可能包含错误处理"}

            # 检查关键C++结构是否保留
            cpp_keywords = ['#include', 'int main', 'class ', 'void ', 'return']
            if any(keyword in original_code for keyword in cpp_keywords):
                preserved_keywords = sum(1 for keyword in cpp_keywords
                                         if keyword in original_code and keyword in fixed_code)
                if preserved_keywords < len([k for k in cpp_keywords if k in original_code]) * 0.5:
                    return {"is_valid": False, "message": "修复后丢失关键C++结构"}

            # C++代码长度变化容忍度更高
            if len(fixed_code) < len(original_code) * 0.3:
                return {"is_valid": False, "message": "修复后代码过短"}

            return {"is_valid": True, "message": "C++修复质量良好"}

        else:  # Python验证
            try:
                compile(fixed_code, '<string>', 'exec')
            except SyntaxError as e:
                return {"is_valid": False, "message": f"修复后代码语法错误: {str(e)}"}

            return {"is_valid": True, "message": "Python修复质量良好"}

    def _evaluate_repair_success(self, original_code: str, fixed_code: str, changes: List[str], language: str) -> bool:
        """根据语言评估修复成功 - 简化版本"""
        if fixed_code == original_code:
            return False

        if len(fixed_code.strip()) == 0:
            return False

        # 检查是否有明确的失败标记
        failure_indicators = ["失败", "无法", "不可用", "未通过验证", "错误"]
        if any(any(indicator in str(change) for change in changes) for indicator in failure_indicators):
            return False

        # 基本成功标准
        return (fixed_code != original_code and
                len(fixed_code.strip()) > 0 and
                len(changes) > 0)

    # ============================================================================
    # 🛠️ 辅助工具模块
    # ============================================================================

    def get_fix_results(self) -> List[Dict]:
        """获取修复结果"""
        return self.fix_results

    def clear_results(self):
        """清空修复结果"""
        self.fix_results = []
        logger.info("已清空修复结果")

    def _find_file_defects(self, file_path: str, defect_report: DefectReport) -> Optional[FileDefects]:
        """
        🛠️ 辅助工具: 查找文件缺陷
        -----------------------
        功能: 在缺陷报告中定位指定文件的缺陷
        优化点: 支持模糊路径匹配
        """
        for file_defects in defect_report.files:
            if file_defects.file_path == file_path:
                return file_defects
        return None

    def _extract_code_snippet(self, full_code: str, line_number: int, context_lines: int = 5) -> str:
        """
        🛠️ 辅助工具: 代码片段提取
        -----------------------
        功能: 提取指定行号附近的代码片段
        参数:
          - context_lines: 上下文行数
        """
        try:
            lines = full_code.split('\n')
            if not lines or line_number <= 0 or line_number > len(lines):
                return f"无效的行号: {line_number} (总行数: {len(lines)})"

            start_line = max(0, line_number - context_lines - 1)
            end_line = min(len(lines), line_number + context_lines)

            snippet_lines = []
            for i in range(start_line, end_line):
                line_num = i + 1
                # 标记目标行
                marker = ">>> " if line_num == line_number else "    "
                line_content = lines[i].rstrip()
                snippet_lines.append(f"{marker}L{line_num:3d}: {line_content}")

            return '\n'.join(snippet_lines)
        except Exception as e:
            logger.error(f"提取代码片段失败: {str(e)}")
            return f"提取代码片段失败: {str(e)}"

    def _extract_variable_from_message(self, message: str, current_line: str) -> str:
        """
        🛠️ 辅助工具: 从消息中提取变量名
        -----------------------------
        功能: 从缺陷消息中智能提取变量名
        方法: 正则匹配 + 上下文分析
        """
        message_lower = message.lower()
        current_line_lower = current_line.lower()

        print(f"DEBUG: 提取变量 - 消息: '{message}', 当前行: '{current_line}'")

        # 1. 首先从消息中明确提到的变量名提取
        # 匹配: 参数'data'、变量'items'、'data'参数 等模式
        explicit_patterns = [
            r"参数\s*['\"`](\w+)['\"`]",  # 参数'data'
            r"变量\s*['\"`](\w+)['\"`]",  # 变量'items'
            r"['\"`](\w+)['\"`]\s*参数",  # 'data'参数
            r"['\"`](\w+)['\"`]\s*变量",  # 'items'变量
            r"parameter\s*['\"`]?(\w+)['\"`]?",  # parameter 'data'
            r"variable\s*['\"`]?(\w+)['\"`]?",  # variable 'items'
        ]

        for pattern in explicit_patterns:
            match = re.search(pattern, message_lower)
            if match:
                variable = match.group(1)
                print(f"DEBUG: 从消息中提取到明确变量: '{variable}'")
                return variable

        # 2. 从函数参数中提取
        if "参数" in message_lower or "parameter" in message_lower:
            # 向上查找函数定义
            lines = current_line.split('\n') if '\n' in current_line else [current_line]
            for line in lines:
                func_match = re.search(r'def\s+\w+\(\s*[^)]*\b(\w+)\b', line)
                if func_match:
                    variable = func_match.group(1)
                    print(f"DEBUG: 从函数参数中提取变量: '{variable}'")
                    return variable

        # 3. 从当前行的使用模式中提取
        # 避免提取方法名 (如 upper(), lower(), strip() 等)
        common_methods = {'upper', 'lower', 'strip', 'split', 'join', 'append', 'pop', 'get', 'items', 'keys', 'values'}

        # 匹配变量使用模式 (排除方法调用)
        usage_patterns = [
            r'\b(\w+)\s*[^=!<>]=[^=]',  # 变量赋值 (但不包含比较)
            r'return\s+(\w+)\b',  # return 语句
            r'if\s+(\w+)\b',  # if 条件
            r'for\s+(\w+)\s+in',  # for 循环
            r'\b(\w+)\s*\[',  # 索引访问
            r'\b(\w+)\s*\.\s*\w+\s*\(',  # 方法调用的主体
        ]

        for pattern in usage_patterns:
            matches = re.findall(pattern, current_line_lower)
            for match in matches:
                if match not in common_methods and len(match) > 1:  # 排除短变量名和方法名
                    print(f"DEBUG: 从使用模式中提取变量: '{match}'")
                    return match

        # 4. 最后从消息中提取任何看起来合理的变量名
        words = re.findall(r'\b[a-z_][a-z0-9_]{1,}\b', message_lower)  # 至少2个字符
        exclude_words = {'none', 'null', 'parameter', 'variable', 'check', 'missing', 'lack', 'missing',
                         'should', 'could', 'would', 'this', 'that', 'the', 'and', 'or', 'but'}

        for word in words:
            if (word not in exclude_words and
                    len(word) > 2 and
                    word not in common_methods and
                    not word.isdigit()):
                print(f"DEBUG: 从消息单词中提取变量: '{word}'")
                return word

        print("DEBUG: 未能提取到变量")
        return ""

    def _is_function_parameter_context(self, lines: List[str], line_index: int) -> bool:
        """
        🛠️ 辅助工具: 判断函数参数上下文
        -----------------------------
        功能: 判断当前行是否在函数参数定义附近
        方法: 向上查找函数定义
        """
        # 检查当前行或之前的行是否有函数定义
        for i in range(line_index, max(-1, line_index - 10), -1):
            if i < 0 or i >= len(lines):
                continue
            line = lines[i]
            if line.strip().startswith('def '):
                return True
            if line.strip().startswith('class '):
                return False
        return False

    def _find_function_body_start(self, lines: List[str], line_index: int) -> int:
        """
        🛠️ 辅助工具: 查找函数体开始位置
        -----------------------------
        功能: 找到函数定义的函数体开始行
        方法: 查找冒号和缩进变化
        """
        # 从当前行向上找到函数定义
        func_def_line = -1
        for i in range(line_index, max(-1, line_index - 10), -1):
            if i < 0 or i >= len(lines):
                continue
            if lines[i].strip().startswith('def '):
                func_def_line = i
                break

        if func_def_line == -1:
            return -1

        # 找到函数体开始（第一个非空行且缩进增加的行）
        for i in range(func_def_line + 1, min(len(lines), func_def_line + 10)):
            if lines[i].strip() and len(lines[i]) - len(lines[i].lstrip()) > len(
                    lines[func_def_line]) - len(lines[func_def_line].lstrip()):
                return i

        return -1

    def _conservative_ai_fix(self, code: str, defect: Defect, issue_type: str, existing_changes: List[str]) -> Tuple[
        str, List[str]]:
        """
        🛠️ 辅助工具: 保守SQL修复
        ----------------------
        功能: SQL注入问题的保守修复
        特点: 优先保持功能，添加安全注释
        """
        # 构建更明确的提示词，强调保持原有功能
        ai_prompt = f"""请修复以下Python代码中的{issue_type}问题：

    问题：{defect.message}

    重要要求：
    1. 必须保持原有功能完整，不能删除任何必要的代码结构
    2. 对于硬编码密码，使用环境变量替代，但要保留原有变量名和结构
    3. 如果涉及配置字典（如AWS_OPTIONS），保持字典结构不变
    4. 确保修复后的代码能够正常运行
    5. 添加必要的import语句

    需要修复的代码：
    ```python
    {code}
    请返回修复后的完整代码："""
        ai_result = ai_fixer.fix_with_ai(code, ai_prompt, "", "python")

        if ai_result["success"]:
            fixed_code = ai_result["fixed_code"]

            # 验证修复质量
            if self._validate_fix_preserves_structure(code, fixed_code, defect):
                existing_changes.append(f"使用保守AI修复{issue_type}问题")
                return fixed_code, existing_changes
            else:
                print("⚠️ AI修复破坏了代码结构，使用基本修复")
                # AI修复失败时，使用最基本的修复
                return self._basic_secret_fix(code, defect, existing_changes)

        # AI修复也失败时，使用最基本的修复
        print("AI修复失败，使用基本修复")
        return self._basic_secret_fix(code, defect, existing_changes)

    def _basic_secret_fix(self, code: str, defect: Defect, changes: List[str]) -> Tuple[str, List[str]]:
        """
        🎯 辅助策略: 基础安全修复
        -----------------------
        功能: 当复杂修复失败时的备选方案
        方案: 添加安全警告注释
        """
        lines = code.split('\n')
        if 0 < defect.line_number <= len(lines):
            line_index = defect.line_number - 1

            # 在问题行前添加警告注释
            warning_comment = "# 安全警告: 检测到硬编码密码，建议使用环境变量替代"
            if line_index > 0 and not lines[line_index - 1].strip().startswith('#'):
                lines.insert(line_index, warning_comment)
                changes.append("添加安全警告注释")
            elif line_index == 0:
                lines.insert(0, warning_comment)
                changes.append("在文件开头添加安全警告注释")

        fixed_code = '\n'.join(lines)
        changes.append("使用基本修复：添加警告注释")
        return fixed_code, changes

    def _fallback_fix_random_security(self, code: str, defect: Defect, context: Dict) -> Tuple[str, List[str]]:
        """
        🎯 辅助策略: 基础SQL修复
        -----------------------
        功能: SQL修复的最终备选方案
        方案: 添加安全注释警告
        """
        changes = []
        lines = code.split('\n')

        if 0 < defect.line_number <= len(lines):
            line_index = defect.line_number - 1
            original_line = lines[line_index]

            # 替换不安全的随机数调用
            if 'random()' in original_line:
                # 将 random() 替换为 secrets.SystemRandom().random()
                fixed_line = original_line.replace('random()', 'secrets.SystemRandom().random()')
                lines[line_index] = fixed_line
                changes.append("将random()替换为secrets.SystemRandom().random()")

                # 确保导入了secrets
                if not any('import secrets' in line for line in lines):
                    # 在文件开头添加import
                    import_added = False
                    for i, line in enumerate(lines):
                        if line.strip().startswith('import ') or line.strip().startswith('from '):
                            lines.insert(i, 'import secrets')
                            import_added = True
                            break
                    if not import_added:
                        lines.insert(0, 'import secrets')
                    changes.append("添加import secrets")

            elif 'randint' in original_line or 'choice' in original_line:
                # 处理其他随机函数
                fixed_line = original_line
                if 'random.randint' in original_line:
                    fixed_line = original_line.replace('random.randint', 'secrets.randbelow')
                elif 'random.choice' in original_line:
                    fixed_line = original_line.replace('random.choice', 'secrets.choice')

                if fixed_line != original_line:
                    lines[line_index] = fixed_line
                    changes.append("将不安全的随机函数替换为secrets模块的对应函数")

                    # 确保导入了secrets
                    if not any('import secrets' in line for line in lines):
                        for i, line in enumerate(lines):
                            if line.strip().startswith('import ') or line.strip().startswith('from '):
                                lines.insert(i, 'import secrets')
                                break
                        changes.append("添加import secrets")

        fixed_code = '\n'.join(lines)

        if changes:
            return fixed_code, changes
        else:
            return code, ["无法使用规则修复随机数安全问题"]

    def _basic_sql_fix(self, code: str, defect: Defect, changes: List[str]) -> Tuple[str, List[str]]:
        """
        🎯 辅助策略: 基础SQL修复
        -----------------------
        功能: SQL修复的最终备选方案
        方案: 添加安全注释警告
        """
        lines = code.split('\n')
        if 0 < defect.line_number <= len(lines):
            line_index = defect.line_number - 1

            # 在问题行前添加安全注释
            warning_comment = "    # 安全警告: 潜在的SQL注入风险，建议使用参数化查询"
            if line_index > 0 and not lines[line_index - 1].strip().startswith('#'):
                lines.insert(line_index, warning_comment)
                changes.append("添加SQL注入安全警告注释")

        fixed_code = '\n'.join(lines)
        changes.append("使用基本修复：添加安全注释")
        return fixed_code, changes

    def _conservative_sql_fix(self, code: str, defect: Defect, existing_changes: List[str]) -> Tuple[str, List[str]]:
        """
        🎯 辅助策略: 保守SQL修复
        ----------------------
        功能: 安全的SQL修复备选方案
        特点: 确保SQL功能完整性
        """

        ai_prompt = f"""请修复以下Python代码中的SQL注入安全问题：

    问题：{defect.message}

    重要要求：
    1. 使用参数化查询替代字符串格式化
    2. 对于表名和列名，如果无法参数化，请确保它们来自可信来源
    3. 保持原有功能完整
    4. 确保修复后的代码语法正确且能够运行

    需要修复的代码：
    ```python
    {code}
    请返回修复后的完整代码："""
        ai_result = ai_fixer.fix_with_ai(code, ai_prompt, "", "python")

        if ai_result["success"]:
            fixed_code = ai_result["fixed_code"]

            # 验证修复质量
            if self._validate_sql_fix(code, fixed_code):
                existing_changes.append("使用AI修复SQL注入问题")
                return fixed_code, existing_changes
            else:
                print("⚠️ AI修复未通过验证，使用基本修复")
                return self._basic_sql_fix(code, defect, existing_changes)

        print("AI修复失败，使用基本修复")
        return self._basic_sql_fix(code, defect, existing_changes)

    def _evaluate_repair_success(self, original_code: str, fixed_code: str, changes: List[str], language: str) -> bool:
        """根据语言评估修复成功"""
        if fixed_code == original_code:
            return False

        if len(fixed_code.strip()) == 0:
            return False

        # 检查是否有明确的失败标记
        failure_indicators = ["失败", "无法", "不可用", "未通过验证", "未产生实际变化"]
        if any(indicator in str(change) for change in changes for indicator in failure_indicators):
            return False

        # 语言特定的成功标准
        if language == "cpp":
            # C++修复成功标准更宽松
            return (len(fixed_code) > len(original_code) * 0.3 and
                    len(changes) > 0)
        else:
            # Python修复成功标准
            return (fixed_code != original_code and
                    fixed_code.strip() != "" and
                    len(fixed_code) > len(original_code) * 0.5 and
                    len(changes) > 0)

    # ============================================================================
    # 📊 报告生成模块 (已迁移到主系统)
    # ============================================================================

    def _generate_detailed_fix_report(self) -> str:
        """
        📊 报告生成: 详细修复报告
        -----------------------
        功能: 生成包含所有修复详情的报告
        结构:
          - 修复统计
          - 修复详情列表
          - 成功率分析

        注意: 此功能已迁移到主报告系统，保留用于兼容性
        """
        if not self.fix_results:
            return "无修复结果"

        # 创建报告目录
        os.makedirs(self.report_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = os.path.join(self.report_dir, f"fix_report_{timestamp}.txt")

        total_tests = len(self.fix_results)
        passed_tests = sum(1 for result in self.fix_results if result.get('success', False))
        success_rate = (passed_tests / total_tests) * 100 if total_tests > 0 else 0

        # 按缺陷类型和策略统计
        defect_stats = {}
        strategy_stats = {}

        for result in self.fix_results:
            defect_type = result.get('defect_type', 'unknown')
            strategy = result.get('strategy', 'unknown')
            confidence = result.get('confidence', 0)
            success = result.get('success', False)

            # 缺陷类型统计
            if defect_type not in defect_stats:
                defect_stats[defect_type] = {'total': 0, 'passed': 0}
            defect_stats[defect_type]['total'] += 1
            if success:
                defect_stats[defect_type]['passed'] += 1

            # 策略统计
            if strategy not in strategy_stats:
                strategy_stats[strategy] = {'total': 0, 'passed': 0, 'confidence_sum': 0}
            strategy_stats[strategy]['total'] += 1
            strategy_stats[strategy]['confidence_sum'] += confidence
            if success:
                strategy_stats[strategy]['passed'] += 1

        # 生成报告内容
        report_content = []
        report_content.append("=" * 60)
        report_content.append("代码修复Agent详细修复报告")
        report_content.append("=" * 60)
        report_content.append(f"总测试数: {total_tests}")
        report_content.append(f"通过数: {passed_tests}")
        report_content.append(f"成功率: {success_rate:.2f}%")
        report_content.append("")

        # 缺陷类型统计
        report_content.append("按缺陷类型统计:")
        for defect_type, stats in defect_stats.items():
            passed_count = stats['passed']
            total_count = stats['total']
            rate = (passed_count / total_count) * 100 if total_count > 0 else 0
            report_content.append(f"  {defect_type}: {passed_count}/{total_count} ({rate:.2f}%)")
        report_content.append("")

        # 修复策略统计
        report_content.append("按修复策略统计:")
        for strategy, stats in strategy_stats.items():
            passed_count = stats['passed']
            total_count = stats['total']
            rate = (passed_count / total_count) * 100 if total_count > 0 else 0
            avg_confidence = stats['confidence_sum'] / total_count if total_count > 0 else 0
            report_content.append(
                f"  {strategy}: {passed_count}/{total_count} ({rate:.2f}%), 平均置信度: {avg_confidence:.2f}")
        report_content.append("")

        # 详细结果
        report_content.append("详细结果:")
        report_content.append("")

        for i, result in enumerate(self.fix_results, 1):
            file_path = result.get('file_path', '未知文件')
            strategy = result.get('strategy', '未知策略')
            success = result.get('success', False)
            confidence = result.get('confidence', 0)
            changes = result.get('changes_made', [])
            original_code = result.get('original_code_snippet', '')
            fixed_code = result.get('fixed_code_snippet', '')
            defect_message = result.get('defect_message', '')

            report_content.append(f"{i}. {file_path}")
            report_content.append(f"   缺陷描述: {defect_message}")
            report_content.append(f"   状态: {'通过' if success else '失败'}")
            report_content.append(f"   策略: {strategy}")
            report_content.append(f"   置信度: {confidence:.2f}")
            report_content.append(f"   变更: {changes}")

            if original_code and fixed_code:
                report_content.append("   代码比较:")
                report_content.append("   原始代码:")
                for line in original_code.split('\n'):
                    report_content.append(f"     {line}")
                report_content.append("   修复后代码:")
                for line in fixed_code.split('\n'):
                    report_content.append(f"     {line}")
            else:
                report_content.append("   代码比较: 无代码片段")

            report_content.append("")

        # 写入文件
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(report_content))

        return report_path

    # ============================================================================
    # 🔄 多轮修复模块
    # ============================================================================

    def multi_round_fix(self, initial_fix_result: str, feedback: str, max_retries: int = 3) -> str:
        """
        🔄 多轮修复: 迭代修复机制
        -----------------------
        功能: 基于反馈进行多轮修复优化
        流程: 初始修复 -> 反馈分析 -> 再次修复
        """
        try:
            fix_result = FixResult.from_json(initial_fix_result)

            if not ai_fixer.is_available():
                logger.warning("AI修复引擎不可用，无法进行多轮修复")
                return initial_fix_result

            # 使用AI进行多轮修复
            ai_result = ai_fixer.fix_with_ai(
                fix_result.fixed_code,
                f"之前的修复反馈: {feedback}. 请重新修复代码。",
                fix_result.original_code,
                "python"
            )

            if ai_result["success"]:
                new_result = FixResult(
                    file_path=fix_result.file_path,
                    original_code=fix_result.original_code,
                    fixed_code=ai_result["fixed_code"],
                    strategy_used=fix_result.strategy_used + "_round2",
                    changes_made=fix_result.changes_made + [f"根据反馈重新修复: {feedback}"],
                    confidence=min(fix_result.confidence + 0.1, 1.0)
                )
                return new_result.to_json()

            return initial_fix_result

        except Exception as e:
            logger.error(f"多轮修复时发生错误: {str(e)}")
            return initial_fix_result

    # ============================================================================
    # 🔍 代码分析工具模块
    # ============================================================================

    def _is_function_removed(self, original_lines: List[str], fixed_lines: List[str], problem_line: int) -> bool:
        """
        🔍 代码分析: 函数删除检测
        -----------------------
        功能: 检测修复过程中是否意外删除了函数
        方法: 对比修复前后的函数定义
        """
        # 查找问题行周围的函数定义
        func_start = -1
        for i in range(max(0, problem_line - 10), min(len(original_lines), problem_line + 1)):
            if original_lines[i].strip().startswith('def '):
                func_start = i
                break

        if func_start == -1:
            return False

        # 获取函数名
        func_line = original_lines[func_start]
        func_match = re.match(r'def\s+(\w+)', func_line)
        if not func_match:
            return False

        func_name = func_match.group(1)

        # 检查修复后的代码中是否还有这个函数
        return not any(f'def {func_name}' in line for line in fixed_lines)

    # ============================================================================
    # 🔧 C++专用修复模块
    # ============================================================================

    def _fix_cpp_include_issues_strategy(self, code: str, defect: Defect, context: Dict, language: str = "cpp") -> \
    Tuple[str, List[str]]:
        """C++修复: 头文件包含问题 - 完整实现"""
        if language != "cpp":
            return code, [f"头文件修复策略仅支持C++，当前语言: {language}"]

        changes = []
        lines = code.split('\n')

        print(f"🔍 开始C++头文件修复策略: 行号={defect.line_number}")
        print(f"缺陷消息: {defect.message}")

        # 提取缺失的头文件
        missing_headers = self._extract_missing_headers(defect.message)

        for header in missing_headers:
            # 检查是否已经包含该头文件
            header_included = any(f'#include <{header}>' in line or f'#include "{header}"' in line for line in lines)

            if not header_included:
                # 找到合适的插入位置
                insert_pos = self._find_cpp_include_position(lines)
                if insert_pos != -1:
                    include_line = f'#include <{header}>'
                    lines.insert(insert_pos, include_line)
                    changes.append(f"添加头文件包含: {header}")
                    print(f"添加头文件: {include_line}")

        fixed_code = '\n'.join(lines)
        return fixed_code, changes

    def _extract_missing_headers(self, message: str) -> List[str]:
        """从缺陷消息中提取缺失的头文件"""
        headers = []
        patterns = [
            r"Include file:\s*<([^>]+)>",
            r"Unable to find include file:\s*'([^']+)'",
            r"Missing include:\s*<([^>]+)>",
            r"未找到头文件:\s*<([^>]+)>"
        ]

        for pattern in patterns:
            matches = re.findall(pattern, message)
            headers.extend(matches)

        return headers

    def _find_cpp_include_position(self, lines: List[str]) -> int:
        """找到C++头文件插入位置"""
        for i, line in enumerate(lines):
            if line.strip().startswith('#include'):
                continue
            elif line.strip() and not line.strip().startswith('#'):
                return i
            elif line.strip().startswith('#pragma') or line.strip().startswith('//'):
                continue
        return 0

    def _fix_cpp_memory_leak_strategy(self, code: str, defect: Defect, context: Dict, language: str = "cpp") -> Tuple[
        str, List[str]]:
        """C++修复: 内存泄漏问题 - 增强版本"""
        if language != "cpp":
            return code, [f"内存泄漏修复策略仅支持C++，当前语言: {language}"]

        changes = []
        lines = code.split('\n')

        print(f"🔍 开始C++内存泄漏修复策略: 行号={defect.line_number}")
        print(f"缺陷消息: {defect.message}")

        target_line_index = defect.line_number - 1
        if 0 <= target_line_index < len(lines):
            target_line = lines[target_line_index]

            # 检测Qt对象的内存管理问题
            if 'new' in target_line and any(qt_class in target_line for qt_class in ['QObject', 'QWidget', 'QDialog']):
                # 查找对象变量名
                var_match = re.search(r'(\w+)\s*=\s*new\s+(\w+)', target_line)
                if var_match:
                    var_name = var_match.group(1)
                    class_name = var_match.group(2)

                    # 检查是否已经有setParent调用
                    has_parent = any(f'{var_name}->setParent' in line for line in lines)

                    if not has_parent:
                        # 在合适的位置添加setParent
                        # 查找函数开始位置
                        func_start = self._find_cpp_function_start(lines, target_line_index)
                        if func_start != -1:
                            # 在函数开始处查找可能的父对象
                            parent_candidates = []
                            for i in range(func_start, target_line_index):
                                line = lines[i]
                                # 查找可能的父对象（this或者其他QObject派生对象）
                                if 'this' in line or any(
                                        parent_class in line for parent_class in ['QWidget', 'QMainWindow', 'QDialog']):
                                    parent_match = re.search(r'(\w+)\s*[;=]', line)
                                    if parent_match:
                                        parent_candidates.append(parent_match.group(1))

                            if parent_candidates:
                                parent_obj = parent_candidates[-1]  # 使用最后一个找到的候选
                                set_parent_line = f"    {var_name}->setParent({parent_obj});"

                                # 在new操作后插入setParent
                                insert_pos = target_line_index + 1
                                lines.insert(insert_pos, set_parent_line)
                                changes.append(f"为{var_name}对象设置父对象{parent_obj}")
                            else:
                                # 使用this作为父对象
                                set_parent_line = f"    {var_name}->setParent(this);"
                                insert_pos = target_line_index + 1
                                lines.insert(insert_pos, set_parent_line)
                                changes.append(f"为{var_name}对象设置父对象this")

        fixed_code = '\n'.join(lines)

        if not changes:
            # 如果规则修复失败，添加智能指针建议
            comment_line = "    // TODO: 考虑使用智能指针(std::unique_ptr或QPointer)管理内存"
            if target_line_index + 1 < len(lines):
                lines.insert(target_line_index + 1, comment_line)
                changes.append("添加智能指针使用建议")
                fixed_code = '\n'.join(lines)

        return fixed_code, changes

    def _find_new_operation_line(self, lines: List[str], defect_line: int) -> int:
        """查找包含new操作的实际行"""
        # 从缺陷行开始，在附近查找包含new的行
        start_line = max(0, defect_line - 3)
        end_line = min(len(lines), defect_line + 3)

        for i in range(start_line, end_line):
            if 'new ' in lines[i] and not lines[i].strip().startswith('//'):
                return i

        return -1

    def _generic_cpp_memory_fix(self, lines: List[str], line_index: int) -> List[str]:
        """通用C++内存修复"""
        changes = []
        target_line = lines[line_index]

        # 添加通用的内存管理建议
        memory_advice = [
            "    // 内存管理建议:",
            "    // 1. 考虑使用智能指针 (std::unique_ptr, std::shared_ptr)",
            "    // 2. 确保在适当位置调用delete释放内存",
            "    // 3. 对于Qt对象，设置父对象或使用QPointer"
        ]

        # 检查是否已经有类似建议
        has_advice = any("内存管理建议" in line for line in lines[max(0, line_index - 2):line_index + 5])

        if not has_advice:
            for i, advice_line in enumerate(memory_advice):
                lines.insert(line_index + 1 + i, advice_line)
            changes.append("添加内存管理建议")

        return changes

    def _find_cpp_function_end(self, lines: List[str], current_line: int) -> int:
        """查找C++函数结束位置"""
        brace_count = 0
        in_function = False
        function_start = -1

        # 首先找到函数开始
        for i in range(current_line, max(-1, current_line - 10), -1):
            if i < 0 or i >= len(lines):
                continue
            if re.match(r'^\s*\w+\s+\w+\([^)]*\)\s*{?\s*$', lines[i].strip()):
                function_start = i
                break

        if function_start == -1:
            return -1

        # 从函数开始统计括号
        brace_count = 0
        for i in range(function_start, len(lines)):
            line = lines[i]
            brace_count += line.count('{')
            brace_count -= line.count('}')

            if brace_count == 0 and i > function_start:
                return i

        return -1

    def _fix_cpp_syntax_strategy(self, code: str, defect: Defect, context: Dict, language: str = "cpp") -> Tuple[
        str, List[str]]:
        """C++修复: 语法问题 - 完整实现"""
        if language != "cpp":
            return code, [f"语法修复策略仅支持C++，当前语言: {language}"]

        changes = []
        lines = code.split('\n')

        if 0 < defect.line_number <= len(lines):
            line_index = defect.line_number - 1
            target_line = lines[line_index]

            # 修复缺少分号
            if "expected ';'" in defect.message and not target_line.rstrip().endswith(';'):
                if not target_line.strip().startswith('#'):  # 不是预处理指令
                    fixed_line = target_line.rstrip() + ';'
                    lines[line_index] = fixed_line
                    changes.append("添加缺失的分号")

            # 修复作用域问题
            elif "not declared" in defect.message:
                if "cout" in target_line and "std::" not in target_line:
                    fixed_line = target_line.replace("cout", "std::cout")
                    lines[line_index] = fixed_line
                    changes.append("添加std::作用域")

        fixed_code = '\n'.join(lines)
        return fixed_code, changes

    def _fix_cpp_performance_strategy(self, code: str, defect: Defect, context: Dict, language: str = "cpp") -> Tuple[
        str, List[str]]:
        """C++修复: 性能问题 - 完整实现"""
        if language != "cpp":
            return code, [f"性能修复策略仅支持C++，当前语言: {language}"]

        changes = []
        lines = code.split('\n')

        if 0 < defect.line_number <= len(lines):
            line_index = defect.line_number - 1
            target_line = lines[line_index]

            # 范围循环引用修复
            if "范围循环" in defect.message and "引用" in defect.message:
                if 'for' in target_line and 'auto' in target_line and '&' not in target_line:
                    # 简单的引用添加
                    fixed_line = target_line.replace('auto ', 'auto& ')
                    if fixed_line != target_line:
                        lines[line_index] = fixed_line
                        changes.append("在范围循环中添加引用")

        fixed_code = '\n'.join(lines)
        return fixed_code, changes

    def _fix_cpp_code_smell_strategy(self, code: str, defect: Defect, context: Dict, language: str = "cpp") -> Tuple[
        str, List[str]]:
        """C++修复: 代码异味问题 - 完整实现"""
        if language != "cpp":
            return code, [f"代码异味修复策略仅支持C++，当前语言: {language}"]

        changes = []
        lines = code.split('\n')

        # 添加重构建议
        if "文件过长" in defect.message or "函数过长" in defect.message:
            insert_pos = defect.line_number - 1 if defect.line_number > 0 else 0
            suggestion = "// TODO: 考虑重构此代码，拆分为更小的函数或文件"

            if insert_pos < len(lines):
                lines.insert(insert_pos, suggestion)
                changes.append("添加重构建议")

        fixed_code = '\n'.join(lines)
        return fixed_code, changes

    def _fix_cpp_qt_specific_strategy(self, code: str, defect: Defect, context: Dict, language: str = "cpp") -> Tuple[
        str, List[str]]:
        """C++修复: Qt特定问题 - 完整实现"""
        if language != "cpp":
            return code, [f"Qt修复策略仅支持C++，当前语言: {language}"]

        changes = []
        lines = code.split('\n')

        if 0 < defect.line_number <= len(lines):
            line_index = defect.line_number - 1

            # QSqlQuery数据库连接检查
            if "QSqlQuery" in defect.message and "数据库连接" in defect.message:
                # 在QSqlQuery使用前添加连接检查
                check_code = [
                    "    // 检查数据库连接是否有效",
                    "    if (!QSqlDatabase::database().isOpen()) {",
                    "        qDebug() << \"数据库连接未打开\";",
                    "        return; // 或适当的错误处理",
                    "    }"
                ]

                # 找到合适的位置插入
                for i, check_line in enumerate(check_code):
                    lines.insert(line_index + i, check_line)
                changes.append("添加数据库连接检查")

        fixed_code = '\n'.join(lines)
        return fixed_code, changes

    def _find_cpp_function_start(self, lines: List[str], current_line: int) -> int:
        """
        查找C++函数开始位置
        """
        for i in range(current_line, max(-1, current_line - 20), -1):
            if i < 0 or i >= len(lines):
                continue
            if re.match(r'^\s*\w+\s+\w+\([^)]*\)\s*{?\s*$', lines[i].strip()):
                return i + 1 if '{' in lines[i] else i
        return -1