# -*- coding: utf-8 -*-
"""
db_adapter_github.py — Lớp tương thích cơ sở dữ liệu VKS BOT cho GITHUB ACTIONS
=============================================================================
Chỉ giữ lại kết nối tới PostgreSQL đám mây. Loại bỏ hoàn toàn SQLite.
Nạp các thông số kết nối từ GitHub Secrets thông qua các biến môi trường.
=============================================================================
"""

import os
import sys
import psycopg2
import psycopg2.extras
import psycopg2.errors

# Đảm bảo in tiếng Việt chuẩn trên Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Đọc cấu hình từ GitHub Secrets (hoặc biến môi trường hệ thống)
DATABASE_URL = os.getenv("DATABASE_URL")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

def get_conn():
    """
    Tạo và trả về kết nối PostgreSQL.
    Hỗ trợ kết nối bằng DATABASE_URL (chuỗi URL đầy đủ) hoặc các thông số riêng lẻ.
    Thiết lập timeout 10 giây để tránh làm treo Workflow GitHub Actions khi mất kết nối mạng.
    """
    try:
        if DATABASE_URL:
            conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
        elif DB_HOST and DB_USER and DB_PASSWORD and DB_NAME:
            conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASSWORD,
                dbname=DB_NAME,
                connect_timeout=10
            )
        else:
            raise ValueError(
                "❌ Không tìm thấy thông số cấu hình PostgreSQL! "
                "Vui lòng thiết lập DATABASE_URL hoặc các biến DB_HOST, DB_USER, DB_PASSWORD, DB_NAME trong GitHub Secrets."
            )
        conn.autocommit = False
        return conn
    except Exception as e:
        print(f"❌ Lỗi kết nối PostgreSQL đám mây: {e}")
        raise

def dict_cursor(conn):
    """Trả về cursor tự động trả kết quả dạng dict (RealDictCursor)."""
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

def rows_to_dicts(rows) -> list:
    """Chuyển danh sách kết quả sang list[dict]."""
    return [dict(r) for r in rows]

def ph() -> str:
    """Ký tự placeholder cho PostgreSQL (%s)."""
    return "%s"

def now_expr() -> str:
    """Biểu thức lấy thời gian hiện tại trong PostgreSQL."""
    return "NOW()"

def integrity_error_class():
    """Trả về class exception lỗi trùng khóa của PostgreSQL."""
    return psycopg2.errors.UniqueViolation

def insert_or_ignore(table: str, columns: list, values: list, conflict_col: str = None):
    """Trả về câu lệnh INSERT an toàn, tự động bỏ qua khi trùng khóa chính trên PostgreSQL."""
    ph_str = ", ".join([ph()] * len(values))
    col_str = ", ".join(columns)
    sql = f"INSERT INTO {table} ({col_str}) VALUES ({ph_str}) ON CONFLICT DO NOTHING"
    return sql, values

def serial_pk() -> str:
    """Kiểu khóa chính tự tăng của PostgreSQL."""
    return "SERIAL PRIMARY KEY"

def execute_safe(cursor, sql: str, params=None):
    """
    Thực thi câu lệnh SQL an toàn, bỏ qua lỗi trùng khóa.
    Trả về True nếu thành công, False nếu trùng khóa.
    """
    try:
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        return True
    except Exception as e:
        if isinstance(e, integrity_error_class()):
            return False
        raise

def is_postgres() -> bool:
    """Đóng vai trò xác thực đang chạy trên PostgreSQL."""
    return True
