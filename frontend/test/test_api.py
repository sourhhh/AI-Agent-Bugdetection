# test_api.py
import requests

base_url = "http://localhost:5000"

# 测试所有可能的端点
endpoints = [
    "/api/health",
    "/health",
    "/api/fix",
    "/fix",
    "/",
    "/api/",
]

for endpoint in endpoints:
    try:
        url = base_url + endpoint
        print(f"测试: {url}")
        response = requests.get(url, timeout=5)
        print(f"状态码: {response.status_code}")
        if response.status_code == 200:
            print(f"响应: {response.text[:100]}...")
        print("-" * 50)
    except Exception as e:
        print(f"错误: {str(e)}")
        print("-" * 50)