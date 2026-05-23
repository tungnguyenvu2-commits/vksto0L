# -*- coding: utf-8 -*-
"""
db_adapter_github.py — Lớp kết nối PostgreSQL chuyên biệt cho GITHUB ACTIONS.
Tích hợp cơ chế tự động tạo bản sao các bảng (_clone) và định tuyến câu lệnh SQL thông minh.
"""

import os
import re
import sys
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", 5432)
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

# Danh sách các bảng cần được theo dõi và định tuyến
TABLES_TO_CLONE = []

class CloneTableCursorWrapper:
    def __init__(self, real_cursor, tables_to_clone):
        self._real_cursor = real_cursor
        self._tables_to_clone = tables_to_clone

    def _rewrite_query(self, query):
        if not query or os.getenv("DB_CLONE_MODE") != "true" or not self._tables_to_clone:
            return query
            
        pattern = r'\b(' + '|'.join(re.escape(t) for t in self._tables_to_clone) + r')\b'
        
        if isinstance(query, bytes):
            query_str = query.decode('utf-8')
            query_str = re.sub(pattern, r'\1_clone', query_str)
            return query_str.encode('utf-8')
        elif isinstance(query, str):
            return re.sub(pattern, r'\1_clone', query)
        return query

    def execute(self, query, vars=None):
        query = self._rewrite_query(query)
        if vars is not None:
            return self._real_cursor.execute(query, vars)
        else:
            return self._real_cursor.execute(query)

    def executemany(self, query, vars_list):
        query = self._rewrite_query(query)
        return self._real_cursor.executemany(query, vars_list)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            return self._real_cursor.__exit__(exc_type, exc_val, exc_tb)
        except AttributeError:
            pass

    def __getattr__(self, name):
        return getattr(self._real_cursor, name)


class CloneTableConnectionWrapper:
    def __init__(self, real_conn, tables_to_clone):
        self._real_conn = real_conn
        self._tables_to_clone = tables_to_clone

    def cursor(self, *args, **kwargs):
        real_cur = self._real_conn.cursor(*args, **kwargs)
        return CloneTableCursorWrapper(real_cur, self._tables_to_clone)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            return self._real_conn.__exit__(exc_type, exc_val, exc_tb)
        except AttributeError:
            pass

    def __getattr__(self, name):
        return getattr(self._real_conn, name)


def auto_clone_all_tables(conn):
    """
    Tự động tạo bản sao (_clone) cho toàn bộ các bảng hiện có trong database PostgreSQL.
    Giữ nguyên cấu trúc, index, constraints của bảng gốc.
    Tự động định vị lại các khóa ngoại tham chiếu chéo giữa các bảng clone.
    """
    real_conn = conn._real_conn if hasattr(conn, "_real_conn") else conn
    
    with real_conn.cursor() as cursor:
        # 1. Lấy danh sách toàn bộ các bảng gốc (không có hậu tố _clone)
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
              AND table_type = 'BASE TABLE'
              AND NOT table_name LIKE '%_clone'
        """)
        tables = [row[0] for row in cursor.fetchall()]
        
        if not tables:
            return []

        print(f"📦 [DevOps] Phát hiện {len(tables)} bảng gốc cần clone: {tables}")
        
        # 2. Tạo bản sao (LIKE ... INCLUDING ALL) cho từng bảng
        for table in tables:
            clone_name = f"{table}_clone"
            print(f"   🔹 Đang tự động clone cấu trúc bảng {table} -> {clone_name}...")
            cursor.execute(f"CREATE TABLE IF NOT EXISTS {clone_name} (LIKE {table} INCLUDING ALL);")
        
        # 3. Đồng bộ dữ liệu ban đầu từ bảng gốc sang bảng clone (ON CONFLICT DO NOTHING)
        for table in tables:
            clone_name = f"{table}_clone"
            
            # Lấy cột khóa chính hoặc unique đầu tiên
            cursor.execute("""
                SELECT kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                  AND tc.table_schema = kcu.table_schema
                WHERE tc.table_schema = 'public'
                  AND tc.table_name = %s
                  AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE')
                LIMIT 1
            """, (table,))
            row = cursor.fetchone()
            unique_col = row[0] if row else None
            
            # Kiểm tra xem bảng gốc có dữ liệu không
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            
            if count > 0:
                if unique_col:
                    print(f"   🔄 Đồng bộ {count} bản ghi từ {table} sang {clone_name} (ON CONFLICT ({unique_col}) DO NOTHING)...")
                    cursor.execute(f"INSERT INTO {clone_name} SELECT * FROM {table} ON CONFLICT ({unique_col}) DO NOTHING;")
                else:
                    print(f"   🔄 Đồng bộ {count} bản ghi từ {table} sang {clone_name}...")
                    cursor.execute(f"SELECT COUNT(*) FROM {clone_name}")
                    clone_count = cursor.fetchone()[0]
                    if clone_count == 0:
                        cursor.execute(f"INSERT INTO {clone_name} SELECT * FROM {table};")
        
        # 4. Định vị lại các khóa ngoại tham chiếu chéo giữa các bảng clone
        cursor.execute("""
            SELECT
                tc.constraint_name, 
                tc.table_name, 
                kcu.column_name, 
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name 
            FROM 
                information_schema.table_constraints AS tc 
                JOIN information_schema.key_column_usage AS kcu
                  ON tc.constraint_name = kcu.constraint_name
                  AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage AS ccu
                  ON ccu.constraint_name = tc.constraint_name
                  AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = 'public'
              AND tc.table_name LIKE '%_clone'
              AND NOT ccu.table_name LIKE '%_clone';
        """)
        foreign_keys = cursor.fetchall()
        
        for fk in foreign_keys:
            constraint_name, table_name, column_name, foreign_table_name, foreign_column_name = fk
            new_foreign_table = f"{foreign_table_name}_clone"
            print(f"   🔗 Cập nhật khóa ngoại {constraint_name} của {table_name}({column_name}) -> tham chiếu {new_foreign_table}({foreign_column_name})...")
            
            try:
                # Drop constraint cũ
                cursor.execute(f"ALTER TABLE {table_name} DROP CONSTRAINT {constraint_name};")
                # Thêm constraint mới trỏ sang bảng clone
                cursor.execute(f"""
                    ALTER TABLE {table_name} 
                    ADD CONSTRAINT {constraint_name} 
                    FOREIGN KEY ({column_name}) 
                    REFERENCES {new_foreign_table}({foreign_column_name});
                """)
            except Exception as e:
                print(f"   ⚠️ Không thể cập nhật khóa ngoại {constraint_name}: {e}")
                
        real_conn.commit()
        return tables


def get_conn():
    """
    Tạo và trả về kết nối PostgreSQL.
    Nếu đang ở chế độ DB_CLONE_MODE="true", tự động clone toàn bộ database cấu trúc và trả về kết nối được bọc định tuyến.
    """
    global TABLES_TO_CLONE
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
                "❌ Không tìm thấy thông số cấu hình PostgreSQL!"
            )
        conn.autocommit = False
        
        # Nếu ở chế độ clone mode, tự động chạy cấy cấu trúc và lấy danh sách bảng gốc
        if os.getenv("DB_CLONE_MODE") == "true":
            # 1. Chạy clone tự động
            TABLES_TO_CLONE = auto_clone_all_tables(conn)
            # 2. Trả về kết nối được bọc định tuyến
            return CloneTableConnectionWrapper(conn, TABLES_TO_CLONE)
            
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
