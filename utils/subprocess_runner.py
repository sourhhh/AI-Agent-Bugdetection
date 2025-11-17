"""Reliable subprocess helper that runs external tools.

For common Python CLI tools (pylint, bandit, mypy, flake8, ruff, pytest, etc.),
we prefer to invoke them via the current Python interpreter as a module
(`sys.executable -m <tool>`) so virtualenv-installed tools are found even when
the PATH does not contain the tool script.
"""
import subprocess
import sys
import json
from typing import Optional, Any
import logging

logger = logging.getLogger(__name__)


def run_command(command: list) -> Optional[Any]:
    """Run a command robustly and return parsed JSON when applicable.

    Returns:
      - parsed JSON if stdout is JSON
      - raw text output for tools like cppcheck when not expecting JSON
      - dict(status=success) when returncode==0 and no output
      - None on error/timeouts
    """
    try:
        if not command:
            return None

        # detect cppcheck
        is_cppcheck = any("cppcheck" in (str(c).lower()) for c in command)

        # python-based CLI tools that we should call via `python -m`
        python_tools = {"pylint", "bandit", "mypy", "prospector", "flake8", "ruff", "pytest"}
        if isinstance(command[0], str):
            base_cmd = command[0].lower()
            for tool in python_tools:
                if base_cmd == tool or base_cmd.startswith(tool):
                    command = [sys.executable, "-m", tool] + command[1:]
                    logger.debug("Converted command to python -m: %s", " ".join(command))
                    break

        expects_json = any("json" in str(c).lower() for c in command)

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            timeout=60,
            check=False,
        )

        # cppcheck sometimes writes to stderr and doesn't use JSON by default
        if is_cppcheck and not expects_json:
            output = (result.stdout or '') + (result.stderr or '')
            return output if output.strip() else None

        stdout = (result.stdout or '').strip()
        if stdout:
            try:
                return json.loads(stdout)
            except json.JSONDecodeError:
                if result.returncode == 0:
                    return result.stdout
                return None

        if result.returncode == 0:
            return {"status": "success", "message": "工具未检测到缺陷"}

        if is_cppcheck and (result.stdout or result.stderr):
            return result.stdout or result.stderr

        logger.warning("Command failed (code %s): %s", result.returncode, command)
        return None

    except subprocess.TimeoutExpired:
        logger.error("Command timeout: %s", command)
        return None
    except Exception as e:
        logger.error("Command exception: %s -> %s", command, str(e))
        return None
