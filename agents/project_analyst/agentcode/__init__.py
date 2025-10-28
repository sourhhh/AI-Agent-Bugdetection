__version__ = "0.1.0"
__author__ = ""  # 可添加作者信息

from .analyzer import ProjectAnalyst
from .deepseek import DeepSeekClient
from .schemas.project_context import ProjectContext  
from .utils.parsers import parse_requirements