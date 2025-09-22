# utils/subprocess_utils.py
import subprocess
import json
from typing import Optional, Dict


def run_command(command: list) -> Optional[Dict]:
    """
    安全执行命令行工具（支撑B角色静态工具集成需求）
    用于调用pylint和bandit，返回解析后的JSON结果
    :param command: 命令列表（如["pylint", "--output-format=json", "test.py"]）
    :return: 工具输出的JSON字典；执行失败/非JSON输出则返回None
    """
    try:
        # 执行命令：捕获输出、超时保护、检查返回码
        result = subprocess.run(
            command,
            capture_output=True,  # 捕获stdout和stderr
            text=True,  # 输出为字符串（而非字节）
            timeout=30,  # 30秒超时（避免工具卡死）
            check=True  # 命令返回非0码时抛出异常
        )

        # 解析工具输出的JSON（静态工具需配置--output-format=json或-f json）
        if result.stdout.strip():
            return json.loads(result.stdout)

        # 工具无输出但执行成功
        return {"status": "success", "message": "工具未检测到缺陷"}

    except subprocess.TimeoutExpired:
        print(f"❌ 命令执行超时：{' '.join(command)}")
        return None
    except subprocess.CalledProcessError as e:
        # 静态工具检测到缺陷时可能返回非0码，尝试解析stdout中的结果
        print(f"⚠️  工具检测到问题：{' '.join(command)} -> {e.stderr[:100]}")
        if e.stdout.strip():
            try:
                return json.loads(e.stdout)
            except json.JSONDecodeError:
                pass
        return None
    except json.JSONDecodeError:
        print(f"❌ 工具输出不是JSON格式：{' '.join(command)}")
        return None
    except Exception as e:
        print(f"❌ 命令执行异常：{' '.join(command)} -> {str(e)}")
        return None