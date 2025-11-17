import os
from core.deepseek_interface import deepseek_client

# 验证环境变量是否被正确读取
print("✅ 读取到的API密钥：", deepseek_client.api_key)  # 应显示 sk-xxx...（部分隐藏）

# 测试LLM接口是否可用
try:
    response = deepseek_client.query("请用一句话介绍自己")
    print("✅ LLM调用成功：", response)  # 应返回类似"我是DeepSeek开发的AI助手..."
except Exception as e:
    print("❌ LLM调用失败：", str(e))