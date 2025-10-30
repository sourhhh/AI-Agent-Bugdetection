# emergency_fix.py - 紧急修复版本
import os
import logging


# 强制清理所有状态
def clean_all_status():
    """清理所有状态文件和目录"""
    items_to_clean = [
        "fix_status.json",
        "test_results",
        "large_scale_repair.log"
    ]

    # 清理修复报告
    import glob
    for report_file in glob.glob("repair_report_*.json"):
        items_to_clean.append(report_file)

    for item in items_to_clean:
        if os.path.exists(item):
            try:
                if os.path.isdir(item):
                    import shutil
                    shutil.rmtree(item)
                else:
                    os.remove(item)
                print(f"已清理: {item}")
            except Exception as e:
                print(f"清理失败 {item}: {e}")


if __name__ == "__main__":
    print("🚨 执行紧急状态清理...")
    clean_all_status()
    print("✅ 状态清理完成，现在重新运行 main_optimized.py")