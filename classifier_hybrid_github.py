# -*- coding: utf-8 -*-
"""
classifier_hybrid_github.py — File xử lý phân loại AI độc lập chuyên dụng cho GitHub Actions.
"""
import os
import sys

def classifier_hybrid_github():
    """
    Hàm phân loại tin tức AI kết hợp (hybrid) dành riêng cho GitHub Actions.
    Tự động chuyển hướng truy vấn CSDL sang các bảng _clone khi chạy kiểm thử (CI/CD).
    """
    print("🧠 [DevOps] Bắt đầu kích hoạt classifier_hybrid_github()...")
    if os.getenv("DB_CLONE_MODE") == "true":
        print("🔒 [Kiểm thử] Chế độ kiểm thử hoạt động: Đang chuyển hướng database sang các bảng _clone!")
        
    # Import và thực thi hàm main của classifier_api_github
    try:
        import classifier_api_github
        classifier_api_github.main()
    except Exception as e:
        print(f"❌ Lỗi trong quá trình phân loại: {e}")
        sys.exit(1)

if __name__ == "__main__":
    classifier_hybrid_github()
