"""后端进程管理服务 - 负责启动、停止和监控后端服务进程"""
import subprocess
import sys
import os
import threading
import time
from typing import Optional, Callable
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BackendManager:
    """后端进程管理器类"""
    
    def __init__(self):
        self.backend_process: Optional[subprocess.Popen] = None
        self.output_callback: Optional[Callable[[str], None]] = None
        self.monitor_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
        self.python_exe = sys.executable
    
    def start_backend(self, output_callback: Optional[Callable[[str], None]] = None) -> dict:
        """
        启动后端服务进程
        
        Args:
            output_callback: 输出回调函数，用于实时处理终端输出
            
        Returns:
            dict: 包含状态和消息的字典
        """
        try:
            # 检查是否已经启动
            if self.backend_process and self.backend_process.poll() is None:
                return {"success": True, "message": "后端服务已在运行"}
            
            # 重置停止事件
            self.stop_event.clear()
            
            # 设置输出回调
            self.output_callback = output_callback
            
            # 构建启动命令
            cmd = [
                self.python_exe,
                os.path.join(self.backend_dir, 'app.py')
            ]
            
            logger.info(f"启动后端服务: {' '.join(cmd)}")
            logger.info(f"工作目录: {self.backend_dir}")
            
            # 启动进程
            self.backend_process = subprocess.Popen(
                cmd,
                cwd=self.backend_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            # 启动监控线程
            self.monitor_thread = threading.Thread(
                target=self._monitor_output,
                daemon=True
            )
            self.monitor_thread.start()
            
            # 等待服务启动
            time.sleep(2)
            
            # 检查进程是否还在运行
            if self.backend_process.poll() is not None:
                return {"success": False, "message": "后端服务启动失败，请查看终端输出"}
            
            return {"success": True, "message": "后端服务启动成功"}
            
        except Exception as e:
            logger.error(f"启动后端服务失败: {str(e)}")
            return {"success": False, "message": f"启动失败: {str(e)}"}
    
    def stop_backend(self) -> dict:
        """
        停止后端服务进程
        
        Returns:
            dict: 包含状态和消息的字典
        """
        try:
            if not self.backend_process or self.backend_process.poll() is not None:
                return {"success": False, "message": "后端服务未在运行"}
            
            # 设置停止事件
            self.stop_event.set()
            
            # 尝试优雅关闭
            logger.info("正在停止后端服务...")
            
            # 发送终止信号
            if sys.platform == 'win32':
                # Windows平台使用terminate
                self.backend_process.terminate()
            else:
                # Linux/Mac使用SIGTERM
                self.backend_process.send_signal(subprocess.signal.SIGTERM)
            
            # 等待进程结束，最多等待5秒
            try:
                self.backend_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # 如果超时，强制终止
                logger.warning("后端服务无法正常关闭，强制终止...")
                if sys.platform == 'win32':
                    os.system(f'taskkill /F /T /PID {self.backend_process.pid}')
                else:
                    self.backend_process.kill()
            
            # 等待监控线程结束
            if self.monitor_thread and self.monitor_thread.is_alive():
                self.monitor_thread.join(timeout=2)
            
            # 清理资源
            self.backend_process = None
            self.monitor_thread = None
            
            return {"success": True, "message": "后端服务已停止"}
            
        except Exception as e:
            logger.error(f"停止后端服务失败: {str(e)}")
            return {"success": False, "message": f"停止失败: {str(e)}"}
    
    def _monitor_output(self):
        """
        监控后端进程输出的线程函数
        """
        if not self.backend_process:
            return
        
        try:
            while not self.stop_event.is_set():
                # 读取一行输出
                line = self.backend_process.stdout.readline()
                if not line:
                    # 检查进程是否结束
                    if self.backend_process.poll() is not None:
                        break
                    # 如果没有输出，短暂睡眠
                    time.sleep(0.1)
                    continue
                
                # 处理输出
                line = line.strip()
                if line:
                    logger.info(f"后端输出: {line}")
                    # 调用回调函数
                    if self.output_callback:
                        try:
                            self.output_callback(line)
                        except Exception as e:
                            logger.error(f"输出回调错误: {str(e)}")
            
            # 读取剩余输出
            remaining_output = self.backend_process.stdout.read()
            if remaining_output and self.output_callback:
                try:
                    self.output_callback(remaining_output.strip())
                except Exception as e:
                    logger.error(f"剩余输出回调错误: {str(e)}")
                    
        except Exception as e:
            logger.error(f"监控输出线程错误: {str(e)}")
    
    def is_running(self) -> bool:
        """
        检查后端服务是否正在运行
        
        Returns:
            bool: 如果服务正在运行返回True，否则返回False
        """
        return self.backend_process is not None and self.backend_process.poll() is None
    
    def get_status(self) -> dict:
        """
        获取后端服务状态
        
        Returns:
            dict: 包含运行状态和消息的字典
        """
        is_running = self.is_running()
        status = "运行中" if is_running else "未运行"
        return {
            "running": is_running,
            "status": status
        }
    
    def run_backend_file(self, file_name: str, output_callback: Optional[Callable[[str], None]] = None, args: List[str] = None) -> dict:
        """
        运行特定的后端文件
        
        Args:
            file_name: 要运行的后端文件名
            output_callback: 输出回调函数，用于实时处理终端输出
            args: 传递给后端文件的命令行参数
            
        Returns:
            dict: 包含状态和消息的字典
        """
        try:
            # 重置停止事件
            self.stop_event.clear()
            
            # 设置输出回调
            self.output_callback = output_callback
            
            # 检查文件是否存在
            file_path = os.path.join(self.backend_dir, file_name)
            if not os.path.exists(file_path):
                # 尝试查找后端目录中的文件
                available_files = [f for f in os.listdir(self.backend_dir) if f.endswith('.py')]
                logger.warning(f"文件 {file_name} 不存在，可用文件: {available_files}")
                return {"success": False, "message": f"文件 '{file_name}' 不存在于后端目录中"}
            
            # 构建运行命令
            cmd = [
                self.python_exe,
                file_path
            ]
            
            # 添加额外参数
            if args:
                cmd.extend(args)
            
            logger.info(f"运行后端文件: {' '.join(cmd)}")
            logger.info(f"工作目录: {self.backend_dir}")
            
            # 启动进程
            self.backend_process = subprocess.Popen(
                cmd,
                cwd=self.backend_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            # 启动监控线程
            self.monitor_thread = threading.Thread(
                target=self._monitor_output,
                daemon=True
            )
            self.monitor_thread.start()
            
            # 等待进程完成
            self.backend_process.wait()
            
            # 检查进程是否成功退出
            exit_code = self.backend_process.returncode
            success = exit_code == 0
            
            # 清理资源
            self.backend_process = None
            self.monitor_thread = None
            
            return {
                "success": success,
                "message": f"文件 '{file_name}' 执行{'成功' if success else '失败'}，退出码: {exit_code}"
            }
            
        except Exception as e:
            logger.error(f"运行后端文件失败: {str(e)}")
            # 清理资源
            self.backend_process = None
            self.monitor_thread = None
            return {"success": False, "message": f"执行失败: {str(e)}"}