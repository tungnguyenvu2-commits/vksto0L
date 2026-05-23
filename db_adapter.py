"""
db_adapter.py — Lớp tương thích cơ sở dữ liệu VKS BOT
========================================================
Tự động phát hiện môi trường và sử dụng đúng loại DB:
  - Có biến môi trường DATABASE_URL → PostgreSQL (Render Production)
  - Không có DATABASE_URL         → SQLite (Máy local, dev)
"""
import os
import sqlite3
import sys

# Đảm bảo in tiếng Việt chuẩn trên Windows bằng reconfigure
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Đường dẫn file SQLite cho local dev
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_FILE = os.path.join(BASE_DIR, "crawler_data.db")

# Đọc DATABASE_URL từ môi trường (Render / GitHub Actions)
DATABASE_URL = os.getenv("DATABASE_URL")
is_deployed = os.getenv("RENDER") or os.getenv("GITHUB_ACTIONS") or os.getenv("DEPLOYMENT_ENV")

# Cờ nhận biết đang dùng PostgreSQL hay SQLite (chỉ dùng Postgres trên Deploy/Cloud, dùng SQLite khi chạy cục bộ)
USE_POSTGRES = bool(DATABASE_URL) and bool(is_deployed)

if USE_POSTGRES:
    try:
        import psycopg2
        import psycopg2.extras
        import psycopg2.errors
        PG_AVAILABLE = True
        print("🐘 [db_adapter] Sử dụng PostgreSQL (Render Postgres)")
    except ImportError:
        PG_AVAILABLE = False
        USE_POSTGRES = False
        print("⚠️ [db_adapter] psycopg2 chưa được cài. Fallback sang SQLite.")
else:
    PG_AVAILABLE = False
    print(f"🗄️  [db_adapter] Sử dụng SQLite: {SQLITE_FILE}")


# ─────────────────────────────────────────────
# Hàm tiện ích
# ─────────────────────────────────────────────

def is_postgres() -> bool:
    """Trả về True nếu đang kết nối PostgreSQL."""
    return USE_POSTGRES


def get_conn():
    """
    Tạo và trả về connection phù hợp với môi trường.
    - PostgreSQL: psycopg2 connection (autocommit=False)
    - SQLite:     sqlite3 connection với row_factory = sqlite3.Row
    """
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        return conn
    else:
        conn = sqlite3.connect(SQLITE_FILE)
        conn.row_factory = sqlite3.Row
        return conn


def dict_cursor(conn):
    """
    Trả về cursor tự động trả kết quả dạng dict.
    - PostgreSQL: RealDictCursor
    - SQLite:     cursor thường (đã có row_factory = sqlite3.Row)
    """
    if USE_POSTGRES:
        return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    else:
        return conn.cursor()


def rows_to_dicts(rows) -> list:
    """Chuyển danh sách kết quả sang list[dict]."""
    return [dict(r) for r in rows]


def ph() -> str:
    """Ký tự placeholder cho câu truy vấn SQL."""
    return "%s" if USE_POSTGRES else "?"


def now_expr() -> str:
    """Biểu thức lấy thời gian hiện tại phù hợp với từng DB."""
    return "NOW()" if USE_POSTGRES else "datetime('now')"


def integrity_error_class():
    """Trả về class exception lỗi trùng khóa phù hợp."""
    if USE_POSTGRES:
        return psycopg2.errors.UniqueViolation
    return sqlite3.IntegrityError


def insert_or_ignore(table: str, columns: list, values: list, conflict_col: str = None):
    """
    Trả về (sql, params) cho lệnh INSERT bỏ qua khi trùng.
    - SQLite: INSERT OR IGNORE INTO ...
    - PostgreSQL: INSERT INTO ... ON CONFLICT DO NOTHING
    """
    ph_str = ", ".join([ph()] * len(values))
    col_str = ", ".join(columns)
    if USE_POSTGRES:
        sql = f"INSERT INTO {table} ({col_str}) VALUES ({ph_str}) ON CONFLICT DO NOTHING"
    else:
        sql = f"INSERT OR IGNORE INTO {table} ({col_str}) VALUES ({ph_str})"
    return sql, values


def serial_pk() -> str:
    """Cú pháp tự tăng khóa chính phù hợp với từng DB."""
    return "SERIAL PRIMARY KEY" if USE_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"


def execute_safe(cursor, sql: str, params=None):
    """
    Thực thi câu SQL an toàn, bỏ qua lỗi trùng khóa.
    Trả về True nếu thành công, False nếu trùng.
    """
    try:
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        return True
    except Exception as e:
        err_class = integrity_error_class()
        if isinstance(e, err_class):
            return False
        raise


def db_file_path() -> str:
    """Trả về đường dẫn file SQLite (chỉ dùng local)."""
    return SQLITE_FILE
