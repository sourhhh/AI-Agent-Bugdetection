"""Compatibility wrapper for subprocess helper.

This module used to contain a direct subprocess implementation. It became
corrupted/duplicated in edits. We provide a thin wrapper that delegates to
`utils.subprocess_runner.run_command` to keep imports in the codebase working
without duplicating logic.
"""
from typing import Optional, Any
import logging

from utils.subprocess_runner import run_command as _run_command

logger = logging.getLogger(__name__)


def run_command(command: list) -> Optional[Any]:
    """Delegate to the central subprocess runner.

    Keeping this wrapper maintains backward compatibility for modules that
    import `utils.subprocess_utils.run_command`.
    """
    try:
        return _run_command(command)
    except Exception as e:
        logger.error(f"subprocess wrapper error: {e}")
        return None