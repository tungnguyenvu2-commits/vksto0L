# -*- coding: utf-8 -*-
"""
test_crawl_github.py — File cào dữ liệu RSS độc lập chuyên dụng cho GitHub Actions.
"""
import os
import sys

def test_crawl_github():
    """
    Hàm kiểm thử cào dữ liệu RSS của GitHub Actions.
    Tự động chuyển hướng truy vấn CSDL sang các bảng _clone khi chạy kiểm thử (CI/CD).
    """
    print("🚀 [DevOps] Bắt đầu kích hoạt test_crawl_github()...")
    if os.getenv("DB_CLONE_MODE") == "true":
        print("🔒 [Kiểm thử] Chế độ kiểm thử hoạt động: Đang chuyển hướng database sang các bảng _clone!")
        
    # Import và thực thi hàm main của test_crawler_github
    try:
        import test_crawler_github
        test_crawler_github.main()
    except Exception as e:
        print(f"❌ Lỗi trong quá trình cào RSS: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_crawl_github()
