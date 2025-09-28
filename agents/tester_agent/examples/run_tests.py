import json
from tester_agent import TesterAgent

if __name__ == "__main__":
    agent = TesterAgent(config_path="config.json")
    result = agent.run_tests(code_dir="sample_project", test_dir="sample_project/tests")

    print("\n=== 测试结果 ===")
    print(json.dumps(result, indent=2, ensure_ascii=False))
