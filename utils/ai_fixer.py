import requests
import json
import time
import os
import re
import threading
import subprocess
import tempfile
import uuid
import random
from typing import Dict, Tuple, Optional, List
import logging
import traceback

logger = logging.getLogger(__name__)


class AIFixerEngine:
    def __init__(self):
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        self.api_url = "https://api.deepseek.com/chat/completions"
        # 降低重试次数以减少等待与重复成本
        self.max_retries = 2
        self.timeout = 30
        self.total_calls = 0
        self._lock = threading.Lock()
        # 失败记录目录
        self.failed_dir = os.path.join(os.getcwd(), 'failed_ai_calls')
        os.makedirs(self.failed_dir, exist_ok=True)

    def is_available(self) -> bool:
        """检查AI修复引擎是否可用"""
        return bool(self.api_key)

    def extract_pure_code(self, ai_response: str, language: str = "python") -> str:
        """从AI回复中提取纯净的代码"""
        if not ai_response:
            return ""

        text = ai_response.strip()

        # 处理代码块格式
        if '```' in text:
            code_blocks = re.findall(r'```(?:\w+)?\s*(.*?)```', text, re.DOTALL)
            if code_blocks:
                code = code_blocks[-1].strip()
                # 移除可能的语言标识行
                lines = code.split('\n')
                if len(lines) > 1:
                    first_line = lines[0].strip().lower()
                    # 检查是否是语言标识
                    if first_line in ['python', 'py', 'cpp', 'c++', 'c']:
                        return '\n'.join(lines[1:]).strip()
                return code

        return text

    def _build_python_prompt(self, problem_code: str, error_info: str, context_code: str) -> str:
        """构建Python修复提示词"""
        if len(problem_code) > 1500:
            problem_code = problem_code[:1500] + "\n# ... (代码过长，已截断)"

        prompt = f"""请修复以下Python代码中的安全问题，同时确保不破坏原有功能：

安全问题：{error_info}

需要修复的代码：
```python
{problem_code}
重要要求：

1.必须保持原有功能完整，不能删除必要的代码行

2.对于随机数安全问题，使用 import secrets 替代 random 模块

3.对于SQL注入问题，使用参数化查询而不是字符串格式化

4.只返回修复后的完整代码，不要任何解释

5.使用Markdown代码块包裹修复后的代码

6.确保修复后的代码语法正确且能够运行

7.请直接返回修复后的完整代码："""
        return prompt

    def _build_cpp_prompt(self, problem_code: str, error_info: str, context_code: str) -> str:
        """构建C++修复提示词"""
        if len(problem_code) > 1500:
            problem_code = problem_code[:1500] + "\n// ... (代码过长，已截断)"

        prompt = f"""请修复以下C++代码中的问题：
        问题描述: {error_info}

        需要修复的代码:
        {problem_code}
        修复要求:

        1.保持原有功能完整

        2.确保修复后的代码符合C++最佳实践

        3.对于Qt相关代码，遵循Qt的编程规范

        4.对于内存管理问题，优先使用智能指针或正确的父子对象关系

        5.只返回修复后的完整代码，不要任何解释

        6.使用Markdown代码块包裹修复后的代码

        7.请直接返回修复后的C++代码："""
        return prompt

    def _build_java_prompt(self, problem_code: str, error_info: str, context_code: str) -> str:
        """构建Java修复提示词"""
        if len(problem_code) > 1500:
            problem_code = problem_code[:1500] + "\n// ... (代码过长，已截断)"

        prompt = f"""请修复以下Java代码中的问题：
问题描述: {error_info}

需要修复的代码:
{problem_code}
修复要求:

1. 保持原有功能完整
2. 遵循Java最佳实践
3. 对于空指针异常等，添加合适的空值检查或防御性代码
4. 只返回修复后的完整代码，不要任何解释
5. 使用Markdown代码块包裹修复后的代码

请直接返回修复后的Java代码："""
        return prompt

    def fix_with_ai(self, problem_code: str, error_info: str, context_code: str = "", language: str = "auto",
                    extra_instructions: str = "", max_attempts: Optional[int] = None,
                    return_candidates: int = 1) -> Dict:
        """
        AI代码修复引擎 - 支持多种语言
        """
        if not self.is_available():
            return {
                "success": False,
                "fixed_code": problem_code,
                "error_message": "AI修复引擎不可用",
                "original_code": problem_code
            }

        logger.debug(f"开始AI修复，问题: {error_info[:100]}...，语言: {language}")
        logger.debug(f"原始代码长度: {len(problem_code)}")

        # 安全模式控制：由环境变量 AI_SAFE_MODE 控制（默认开启）
        safe_mode_env = os.environ.get('AI_SAFE_MODE', '1')
        safe_mode = not (safe_mode_env == '0' or safe_mode_env.lower() == 'false')

        # 本地参数拷贝（避免修改实例属性）
        local_return_candidates = int(return_candidates) if return_candidates and isinstance(return_candidates, int) else 1
        local_max_retries = int(self.max_retries)
        local_timeout = int(self.timeout)

        if safe_mode:
            # 保守调用：单候选、延长read timeout、限制重试
            local_return_candidates = 1
            # 使用较长的 read timeout，以应对间歇性慢响应
            local_timeout = max(local_timeout, 120)
            local_max_retries = min(local_max_retries, 2)


        # 自动检测语言（如果未指定）
        if language == "auto":
            language = self._detect_language(problem_code)
            logger.debug(f"自动检测到语言: {language}")

        # 检查API调用频率（线程安全）
        with self._lock:
            self.total_calls += 1
            if self.total_calls % 5 == 0:
                time.sleep(2)

        # 构建针对不同语言的提示词
        if language == "cpp":
            prompt = self._build_cpp_prompt(problem_code, error_info, context_code)
        elif language == "java":
            prompt = self._build_java_prompt(problem_code, error_info, context_code)
        else:
            prompt = self._build_python_prompt(problem_code, error_info, context_code)

        # 如果提供了额外指令，则追加到提示词末尾，便于在重试时附加编译器错误或更严格的约束
        if extra_instructions:
            prompt = prompt + "\n\n-- 额外指令: " + extra_instructions

        # 准备API请求数据
        data = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 2000,
            "stream": False
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # 重试机制：指数退避 + 抖动；如果 AI 返回代码但本地验证失败，会把编译/验证错误附加回 prompt 再次请求
        last_response_text = None
        attempts = max_attempts if (isinstance(max_attempts, int) and max_attempts > 0) else local_max_retries
        # 使用局部 attempts 变量进行日志和重试判断
        for attempt in range(attempts):
            try:
                logger.debug(f"AI修复尝试 {attempt + 1}/{attempts} - 语言: {language}")

                response = requests.post(
                    self.api_url,
                    headers=headers,
                    json=data,
                    timeout=(10, local_timeout)
                )

                # 记录基础 HTTP 信息
                http_status = response.status_code
                http_headers = dict(response.headers or {})
                http_body = None
                try:
                    http_body = response.text
                except Exception:
                    http_body = '<unreadable body>'

                if http_status == 200:
                    try:
                        response_data = response.json()
                        ai_response = response_data['choices'][0]['message']['content']
                    except Exception as e:
                        # JSON 解析失败
                        last_response_text = None
                        logger.error(f"无法解析AI响应JSON: {e}")
                        # 如果还有重试机会，继续
                        if attempt < attempts - 1:
                            backoff = (2 ** attempt) + random.uniform(0, 1)
                            time.sleep(backoff)
                            continue
                        else:
                            # 记录失败元数据并退出循环以保存
                            http_error_meta = {
                                'http_status': http_status,
                                'http_headers': http_headers,
                                'http_body': (http_body[:5000] if http_body else None),
                                'parse_error': str(e)
                            }
                            break
                    last_response_text = ai_response

                    # 支持返回多个候选：如果请求 return_candidates>1，模型应当返回多个编号的代码块
                    if local_return_candidates and local_return_candidates > 1:
                        # 尝试解析所有代码块作为候选
                        code_blocks = re.findall(r'```(?:\w+)?\s*(.*?)```', ai_response, re.DOTALL)
                        candidates = [self.extract_pure_code(cb, language) for cb in code_blocks if cb.strip()]
                        # 如果解析不到代码块，尝试用分隔符按数字编号分割
                        if not candidates:
                            parts = re.split(r'\n\s*\d+\)\s*|\n\s*\d+\.|\n\s*Candidate\s+\d+', ai_response)
                            candidates = [self.extract_pure_code(p, language) for p in parts if p.strip()]
                        # 清理并去重
                        seen = set()
                        uniq = []
                        for c in candidates:
                            s = c.strip()
                            if s and s not in seen:
                                seen.add(s)
                                uniq.append(s)
                        candidates = uniq[:local_return_candidates]
                        # 对每个候选做本地验证并返回候选列表供上层选择
                        parsed_candidates = []
                        for c in candidates:
                            ok, validation_output = self._validate_code_locally(c, language)
                            parsed_candidates.append({
                                'code': c,
                                'valid': ok,
                                'validation_output': validation_output
                            })
                        if parsed_candidates:
                            return {
                                'success': True if any(p['valid'] for p in parsed_candidates) else False,
                                'candidates': parsed_candidates,
                                'last_ai_response': ai_response,
                                'original_code': problem_code
                            }

                    fixed_code = self.extract_pure_code(ai_response, language)

                    # 基本有效性检查
                    if not fixed_code or fixed_code == problem_code or len(fixed_code.strip()) <= 10:
                        logger.warning("AI返回的代码无效或与原始代码相同")
                        # 轻抛弃并重试
                    else:
                        # 本地验证（编译/语法检查）
                        ok, validation_output = self._validate_code_locally(fixed_code, language)
                        if ok:
                            # 仅保留简洁的成功信息，详细信息记录为 debug
                            logger.info("AI修复成功")
                            logger.debug(f"AI修复成功且本地验证通过，返回代码长度: {len(fixed_code)}")
                            return {
                                "success": True,
                                "fixed_code": fixed_code,
                                "error_message": None,
                                "original_code": problem_code
                            }
                        else:
                            logger.warning(f"本地验证失败: {validation_output[:200]}")
                            # 如果还有重试机会，将验证输出附加到 prompt，要求模型基于错误信息修复
                            if attempt < self.max_retries - 1:
                                # 附加编译/验证错误信息并重构 prompt
                                suffix = "\n\n-- 本地验证错误信息 (请据此修复并只返回修复后的代码) --\n" + validation_output
                                # 把原始 messages 中的 user 内容追加错误信息
                                data['messages'][0]['content'] = data['messages'][0]['content'] + suffix
                                # 指数退避后继续下一次尝试
                            else:
                                logger.error("达到最大重试次数，放弃本地验证失败的修复")

                elif http_status == 429:
                    # 频率限制，指数退避
                    backoff = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"频率限制(429)，等待{backoff:.1f}秒后重试")
                    time.sleep(backoff)
                    continue
                else:
                    logger.error(f"API错误: {http_status}")
                    # 如果不是最后一次尝试，指数退避后继续
                    if attempt < attempts - 1:
                        backoff = (2 ** attempt) + random.uniform(0, 1)
                        time.sleep(backoff)
                        continue
                    # 最后一次则保留 http body/header 供保存
                    http_error_meta = {
                        'http_status': http_status,
                        'http_headers': http_headers,
                        'http_body': (http_body[:5000] if http_body else None)
                    }

                # 如果未返回成功，等待指数退避并重试
                if attempt < self.max_retries - 1:
                    backoff = (2 ** attempt) + random.uniform(0, 1)
                    time.sleep(backoff)
                    continue

            except requests.exceptions.Timeout:
                logger.warning(f"请求超时 (尝试 {attempt + 1})")
                http_error_meta = {'exception': 'timeout', 'exception_trace': traceback.format_exc()}
                if attempt < self.max_retries - 1:
                    backoff = (2 ** attempt) + random.uniform(0, 1)
                    time.sleep(backoff)
                continue

            except requests.exceptions.ConnectionError:
                logger.warning(f"连接错误 (尝试 {attempt + 1})")
                http_error_meta = {'exception': 'connection_error', 'exception_trace': traceback.format_exc()}
                if attempt < self.max_retries - 1:
                    backoff = (2 ** attempt) + random.uniform(0, 1)
                    time.sleep(backoff)
                continue

            except Exception as e:
                logger.error(f"请求异常: {str(e)}")
                http_error_meta = {'exception': str(e), 'exception_trace': traceback.format_exc()}
                if attempt < self.max_retries - 1:
                    time.sleep(2)
                continue

        # 所有尝试均失败：保存失败请求与最后一次AI响应供人工分析
        # 所有尝试均失败：保存失败请求与最后一次AI响应及HTTP/异常信息供人工分析
        try:
            fid = uuid.uuid4().hex
            meta = {
                'problem_code': problem_code,
                'error_info': error_info,
                'language': language,
                'last_ai_response': last_response_text,
                'timestamp': time.time()
            }
            # 合并 http_error_meta（如果存在），但不要写入 Authorization header 或 API key
            if 'http_error_meta' in locals() and isinstance(http_error_meta, dict):
                meta.update(http_error_meta)
            meta_path = os.path.join(self.failed_dir, f'failed_{fid}.json')
            with open(meta_path, 'w', encoding='utf-8') as fh:
                json.dump(meta, fh, ensure_ascii=False, indent=2)
            logger.debug(f"已保存失败记录: {meta_path}")
        except Exception:
            logger.exception("保存失败记录时出错")

        logger.error("所有AI修复尝试均失败")
        return {
            "success": False,
            "fixed_code": problem_code,
            "error_message": "所有重试尝试均失败",
            "original_code": problem_code
        }

    def _which(self, exe_name: str) -> Optional[str]:
        for path in os.environ.get('PATH', '').split(os.pathsep):
            candidate = os.path.join(path, exe_name)
            if os.path.exists(candidate) and os.access(candidate, os.X_OK):
                return candidate
        return None

    def _try_compile_with(self, compiler: str, code: str, suffix: str = '.tmp', extra_args: List[str] = None) -> Tuple[bool, str]:
        extra_args = extra_args or []
        tmp_dir = tempfile.mkdtemp(prefix='aifix_')
        unique = uuid.uuid4().hex
        file_path = os.path.join(tmp_dir, f'tmp_{unique}{suffix}')
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(code)

            cmd = [compiler] + extra_args + [file_path]
            try:
                proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
                output = (proc.stdout or '') + (proc.stderr or '')
                return (proc.returncode == 0), output
            except Exception as e:
                return False, str(e)
        finally:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                os.rmdir(tmp_dir)
            except Exception:
                pass

    def _validate_code_locally(self, code: str, language: str) -> Tuple[bool, str]:
        """在本地做快速语法/编译检查。返回 (ok, output)。"""
        if not code or len(code.strip()) < 5:
            return False, "代码太短"

        if language == 'python':
            try:
                compile(code, '<string>', 'exec')
                return True, 'python compile ok'
            except SyntaxError as e:
                return False, f'Python SyntaxError: {e}'

        if language == 'java':
            javac = self._which('javac')
            if javac:
                ok, out = self._try_compile_with(javac, code, suffix='.java')
                return ok, out
            # fallback simple check
            if 'class ' in code or 'public static void' in code:
                return True, 'basic java pattern check passed (no javac)'
            return False, 'javac not found and basic checks failed'

        if language == 'cpp':
            gpp = self._which('g++') or self._which('clang++')
            if gpp:
                ok, out = self._try_compile_with(gpp, code, suffix='.cpp', extra_args=['-fsyntax-only'])
                return ok, out
            if any(k in code for k in ['#include', 'int main', 'std::']):
                return True, 'basic cpp pattern check passed (no compiler)'
            return False, 'g++/clang++ not found and basic checks failed'

        return True, 'unknown language - assume ok'

    def _detect_language(self, code: str) -> str:
        """自动检测代码语言"""
        cpp_keywords = ['#include', 'using namespace', 'class ', 'struct ', 'public:', 'private:', 'cout <<', 'endl;']
        python_keywords = ['def ', 'import ', 'from ', 'class ', 'print(', 'lambda ']
        java_keywords = ['public static void', 'System.out.println', 'import java.', 'package ', 'throws', 'NullPointerException']

        cpp_count = sum(1 for keyword in cpp_keywords if keyword in code)
        python_count = sum(1 for keyword in python_keywords if keyword in code)
        java_count = sum(1 for keyword in java_keywords if keyword in code)

        # 返回计数最高的语言
        if java_count > cpp_count and java_count > python_count:
            return "java"
        if cpp_count > python_count and cpp_count >= java_count:
            return "cpp"
        return "python"

    def _which(self, exe_name: str) -> str:
        """查找可执行文件路径，返回None或路径"""
        from shutil import which
        return which(exe_name)

    def _try_compile_with(self, compiler: str, code: str, suffix: str = '.tmp', extra_args: list = None) -> tuple:
        """将代码写入临时文件并用指定编译器检查语法/编译，返回 (ok, output)"""
        extra_args = extra_args or []
        tmp_dir = tempfile.mkdtemp(prefix='aifixer_')
        unique = uuid.uuid4().hex
        file_path = os.path.join(tmp_dir, f'tmp_{unique}{suffix}')
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(code)

            cmd = [compiler] + extra_args + [file_path]
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
            output = (proc.stdout or '') + (proc.stderr or '')
            return (proc.returncode == 0), output
        except Exception as e:
            return False, str(e)
        finally:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                os.rmdir(tmp_dir)
            except Exception:
                pass

    def _validate_code_locally(self, code: str, language: str = 'python') -> tuple:
        """
        本地验证代码：针对 Python 使用 compile()；针对 Java/C++ 尝试调用本地编译器（若可用），否则做轻量模式检查。
        返回 (ok: bool, output: str)
        """
        if not code or len(code.strip()) < 5:
            return False, '代码过短或为空'

        if language == 'python':
            try:
                compile(code, '<string>', 'exec')
                return True, 'Python 语法检查通过'
            except SyntaxError as e:
                return False, f'Python 语法错误: {e}'

        if language == 'java':
            javac = self._which('javac')
            if javac:
                ok, out = self._try_compile_with(javac, code, suffix='.java')
                return ok, out
            # 基础模式检查
            if 'class ' in code or 'public static void' in code:
                return True, 'Java 基础模式检查通过（未找到 javac）'
            return False, '未找到 javac，且代码未通过基础模式检查'

        if language == 'cpp' or language == 'c++':
            gpp = self._which('g++') or self._which('clang++')
            if gpp:
                ok, out = self._try_compile_with(gpp, code, suffix='.cpp', extra_args=['-fsyntax-only'])
                return ok, out
            if any(k in code for k in ['#include', 'int main', 'std::']):
                return True, 'C++ 基础模式检查通过（未找到编译器）'
            return False, '未找到 g++/clang++，且代码未通过基础模式检查'

        # 其他语言默认通过但告知人工复查
        return True, '未识别语言，建议人工复查'

ai_fixer = AIFixerEngine()