# -*- coding: utf-8 -*-
"""
non_scrapper_github.py — File cào dữ liệu phi RSS độc lập chuyên dụng cho GitHub Actions.
"""
import os
import sys

def non_scrapper_github():
    """
    Hàm cào dữ liệu phi RSS của GitHub Actions.
    Tự động chuyển hướng truy vấn CSDL sang các bảng _clone khi chạy kiểm thử (CI/CD).
    """
    print("🕸️ [DevOps] Bắt đầu kích hoạt non_scrapper_github()...")
    if os.getenv("DB_CLONE_MODE") == "true":
        print("🔒 [Kiểm thử] Chế độ kiểm thử hoạt động: Đang chuyển hướng database sang các bảng _clone!")
        
    # Import và thực thi hàm main của non_rss_scraper_github
    try:
        import non_rss_scraper_github
        non_rss_scraper_github.main()
    except Exception as e:
        print(f"❌ Lỗi trong quá trình cào phi RSS: {e}")
        sys.exit(1)

if __name__ == "__main__":
    non_scrapper_github()
