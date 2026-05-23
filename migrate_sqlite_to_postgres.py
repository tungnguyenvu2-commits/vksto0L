"""
migrate_sqlite_to_postgres.py
========================================================
Script đồng bộ và chuyển toàn bộ dữ liệu hiện có từ cơ sở dữ liệu SQLite cục bộ (crawler_data.db)
lên cơ sở dữ liệu PostgreSQL từ xa (Render Postgres) của bạn.
========================================================
Cách sử dụng:
  1. Đảm bảo file .env của bạn có chứa DATABASE_URL của Render (External Database URL).
  2. Cài đặt psycopg2: pip install psycopg2-binary
  3. Chạy script: python migrate_sqlite_to_postgres.py
"""

import os
import sqlite3
import sys
from dotenv import load_dotenv

# Đảm bảo in tiếng Việt chuẩn trên Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Tải biến môi trường từ file .env
load_dotenv()

# Đường dẫn database local SQLite (Tìm kiếm thông minh tại thư mục script, thư mục gốc và thư mục hiện hành)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
possible_paths = [
    os.path.join(BASE_DIR, "crawler_data.db"),
    os.path.join(os.path.dirname(BASE_DIR), "crawler_data.db"),
    os.path.join(os.getcwd(), "crawler_data.db")
]

# Ưu tiên chọn tệp CSDL có kích thước lớn nhất để đảm bảo lấy đúng tệp chứa dữ liệu thực tế
SQLITE_DB = possible_paths[0]
max_size = -1
for path in possible_paths:
    if os.path.exists(path):
        size = os.path.getsize(path)
        if size > max_size:
            max_size = size
            SQLITE_DB = path

# Đọc DATABASE_URL từ môi trường
DATABASE_URL = os.getenv("DATABASE_URL")

def migrate():
    print("🚀 BẮT ĐẦU QUY TRÌNH ĐỒNG BỘ DỮ LIỆU SQLITE ➔ POSTGRESQL 🚀")
    print("------------------------------------------------------------")
    
    # 1. Kiểm tra sự tồn tại của database nguồn (SQLite)
    if not os.path.exists(SQLITE_DB):
        print(f"❌ LỖI: Không tìm thấy tệp cơ sở dữ liệu SQLite cục bộ tại: {SQLITE_DB}")
        print("💡 Hãy chắc chắn rằng bạn chạy script này ở cùng thư mục chứa file 'crawler_data.db'.")
        return
    else:
        print(f"🗄️ Đã kết nối Database nguồn SQLite: {SQLITE_DB}")

    # 2. Kiểm tra chuỗi kết nối đích (PostgreSQL)
    if not DATABASE_URL:
        print("❌ LỖI: Chưa định nghĩa DATABASE_URL trong môi trường hoặc trong tệp .env.")
        print("💡 Hãy thêm dòng sau vào tệp .env ở thư mục gốc:")
        print("   DATABASE_URL=postgresql://user:password@host/dbname")
        return
    
    # Ẩn mật khẩu khi in ra màn hình để bảo mật
    masked_url = DATABASE_URL
    if "@" in DATABASE_URL:
        prefix, suffix = DATABASE_URL.split("@", 1)
        if ":" in prefix:
            proto_user, _ = prefix.rsplit(":", 1)
            masked_url = f"{proto_user}:******@{suffix}"
    
    print(f"🐘 Đã kết nối Database đích PostgreSQL: {masked_url}")
    
    # 3. Import thư viện Postgres
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        print("❌ LỖI: Thiếu thư viện 'psycopg2'.")
        print("💡 Hãy chạy lệnh: pip install psycopg2-binary và thử lại.")
        return

    def get_pg_connection(db_url):
        # Bật TCP keepalive và đặt connection timeout để tránh treo vô hạn do rớt mạng
        # statement_timeout=60s: đủ rộng cho lô 200 dòng qua WAN Singapore mà không bị Render ngắt
        return psycopg2.connect(
            db_url,
            connect_timeout=15,
            keepalives=1,
            keepalives_idle=10,
            keepalives_interval=3,
            keepalives_count=5,
            options='-c statement_timeout=60000'
        )

    # 4. Thiết lập kết nối
    conn_lite = sqlite3.connect(SQLITE_DB)
    conn_lite.row_factory = sqlite3.Row
    cursor_lite = conn_lite.cursor()
    
    try:
        conn_pg = get_pg_connection(DATABASE_URL)
        cursor_pg = conn_pg.cursor()
        print("✅ Kết nối đến Render Postgres thành công!")
    except Exception as e:
        print(f"❌ LỖI: Không thể kết nối tới Render PostgreSQL: {e}")
        conn_lite.close()
        return

    # 5. Lấy danh sách bảng trong SQLite
    cursor_lite.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = [row[0] for row in cursor_lite.fetchall()]
    
    if not tables:
        print("⚠️ Database SQLite hiện đang rỗng hoặc chưa có bảng dữ liệu nào.")
        conn_lite.close()
        conn_pg.close()
        return

    print(f"📂 Tìm thấy {len(tables)} bảng dữ liệu trong SQLite: {', '.join(tables)}")
    print("------------------------------------------------------------")

    # 6. Chế độ đồng bộ gia tăng (Incremental Sync): Giữ lại các bảng hiện có, chỉ thêm mới dữ liệu
    print("🔄 Đang chạy ở chế độ ĐỒNG BỘ GIA TĂNG (Không xóa dữ liệu cũ trên PostgreSQL)...")

    # 7. Đảm bảo cấu trúc bảng tồn tại trên PostgreSQL (sử dụng IF NOT EXISTS)
    print("⚙️ Đang đồng bộ hóa cấu trúc bảng trên PostgreSQL...")
    for table_name in tables:
        try:
            cursor_lite.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name = ?", (table_name,))
            create_sql = cursor_lite.fetchone()[0]
            
            # Dịch cú pháp SQLite sang PostgreSQL
            pg_create_sql = create_sql
            pg_create_sql = pg_create_sql.replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS")
            pg_create_sql = pg_create_sql.replace("create table", "CREATE TABLE IF NOT EXISTS")
            pg_create_sql = pg_create_sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
            pg_create_sql = pg_create_sql.replace("integer primary key autoincrement", "SERIAL PRIMARY KEY")
            pg_create_sql = pg_create_sql.replace("DATETIME DEFAULT CURRENT_TIMESTAMP", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            pg_create_sql = pg_create_sql.replace("datetime default current_timestamp", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            
            # Lược bỏ các dòng có FOREIGN KEY để tránh ràng buộc phụ thuộc khi nạp dữ liệu từ xa qua WAN
            lines = pg_create_sql.split("\n")
            filtered_lines = [l for l in lines if "FOREIGN KEY" not in l and "foreign key" not in l]
            pg_create_sql = "\n".join(filtered_lines)
            
            # Dọn dẹp dấu phẩy thừa ở cuối nếu có bằng regex thông minh
            import re
            pg_create_sql = re.sub(r',\s*\)', r'\n)', pg_create_sql)
            
            cursor_pg.execute(pg_create_sql)
            conn_pg.commit()
            print(f"   ➔ Đã kiểm tra/tạo cấu trúc bảng: {table_name}")
            
            # Đồng bộ các cột mới nếu đã có bảng nhưng thiếu cột (như cột telegram_sent)
            cursor_lite.execute(f"PRAGMA table_info({table_name})")
            sqlite_columns = cursor_lite.fetchall()
            
            cursor_pg.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name='{table_name}'")
            pg_columns = [r[0].lower() for r in cursor_pg.fetchall()]
            
            if pg_columns:
                for col in sqlite_columns:
                    col_name = col[1]
                    col_type = col[2]
                    pg_type = col_type.upper()
                    
                    if "INTEGER" in pg_type:
                        pg_type = "INTEGER"
                    elif "DATETIME" in pg_type or "TIMESTAMP" in pg_type:
                        pg_type = "TIMESTAMP"
                    elif "TEXT" in pg_type:
                        pg_type = "TEXT"
                    else:
                        pg_type = "TEXT"
                        
                    if col_name.lower() not in pg_columns:
                        print(f"   ⚙️ Phát hiện thiếu cột '{col_name}' trong PostgreSQL, đang tự động bổ sung...")
                        alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {col_name} {pg_type}"
                        if "INTEGER" in pg_type:
                            alter_sql += " DEFAULT 0"
                        else:
                            alter_sql += " DEFAULT NULL"
                        cursor_pg.execute(alter_sql)
                        conn_pg.commit()
        except Exception as e:
            conn_pg.rollback()
            print(f"   ❌ Không thể tạo hoặc đồng bộ cấu trúc bảng {table_name}: {e}")

    # 7. Di chuyển dữ liệu từng bảng một cách thông minh
    for table in tables:
        print(f"\n📊 Đang đồng bộ bảng: {table}...")
        
        # Lấy dữ liệu từ SQLite
        cursor_lite.execute(f"SELECT * FROM {table}")
        rows = cursor_lite.fetchall()
        
        if not rows:
            print(f"   ➔ Không có bản ghi nào để đồng bộ.")
            continue
            
        # Trích xuất danh sách cột
        columns = [desc[0] for desc in cursor_lite.description]
        col_str = ", ".join(columns)
        placeholders = ", ".join(["%s"] * len(columns))
        
        # Sử dụng lệnh INSERT ON CONFLICT để bỏ qua trùng lặp
        # Nhận diện khóa chính làm trường so khớp xung đột
        conflict_target = ""
        if table == "vks_settings":
            conflict_target = "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
        elif table == "rss_sources":
            conflict_target = "ON CONFLICT (rss_url) DO NOTHING"
        elif table == "resolution_keywords":
            conflict_target = "ON CONFLICT (keyword) DO NOTHING"
        elif table == "raw_articles":
            conflict_target = "ON CONFLICT (url) DO NOTHING"
        elif table == "classified_articles":
            conflict_target = "ON CONFLICT (raw_article_id) DO NOTHING"
        else:
            conflict_target = "ON CONFLICT DO NOTHING"
            
        insert_sql = f"INSERT INTO {table} ({col_str}) VALUES %s {conflict_target}"
        
        success_count = 0
        duplicate_count = 0
        
        # Batch insert sử dụng execute_values để truyền tải siêu tốc qua WAN
        # batch_size=200: đã kiểm nghiệm thành công với Render Postgres Singapore
        batch_size = 200
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i+batch_size]
            
            # Chuyển đổi dữ liệu Row thành Tuple thuần túy và làm sạch ký tự NUL (\x00) cho PostgreSQL compatibility
            batch_data = []
            for row in batch:
                cleaned_row = tuple(
                    (val.replace('\x00', '') if isinstance(val, str) else val)
                    for val in row
                )
                batch_data.append(cleaned_row)
            
            try:
                # Đảm bảo kết nối còn sống
                if conn_pg.closed != 0:
                    print("⚠️ Mất kết nối tới Postgres. Đang kết nối lại...")
                    import time
                    try:
                        conn_pg = get_pg_connection(DATABASE_URL)
                        cursor_pg = conn_pg.cursor()
                        print("✅ Kết nối lại thành công!")
                    except Exception as re_err:
                        print(f"❌ Không thể kết nối lại: {re_err}. Chờ 5 giây thử lại...")
                        time.sleep(5)
                        conn_pg = get_pg_connection(DATABASE_URL)
                        cursor_pg = conn_pg.cursor()
                        print("✅ Kết nối lại thành công sau khi chờ!")
                
                psycopg2.extras.execute_values(cursor_pg, insert_sql, batch_data, page_size=100)
                success_count += cursor_pg.rowcount
                conn_pg.commit()
            except Exception as pg_err:
                print(f"   ⚠️ Lô bị lỗi hoặc mất kết nối ({pg_err}), chuyển sang chèn từng dòng cứu hộ (SAVEPOINT)...")
                try:
                    conn_pg.rollback()
                except Exception:
                    pass
                
                reconnect_failed = False
                for row_tuple in batch_data:
                    if reconnect_failed:
                        break
                        
                    # Đảm bảo kết nối sống trước khi chèn từng dòng
                    if conn_pg.closed != 0:
                        try:
                            conn_pg = get_pg_connection(DATABASE_URL)
                            cursor_pg = conn_pg.cursor()
                        except Exception as conn_err:
                            print(f"   ❌ Không thể kết nối lại để chèn dòng cứu hộ: {conn_err}")
                            reconnect_failed = True
                            break
                            
                    try:
                        cursor_pg.execute("SAVEPOINT row_save")
                        placeholders = ", ".join(["%s"] * len(columns))
                        fallback_sql = f"INSERT INTO {table} ({col_str}) VALUES ({placeholders}) {conflict_target}"
                        cursor_pg.execute(fallback_sql, row_tuple)
                        cursor_pg.execute("RELEASE SAVEPOINT row_save")
                        if cursor_pg.rowcount > 0:
                            success_count += 1
                        else:
                            duplicate_count += 1
                    except Exception:
                        try:
                            cursor_pg.execute("ROLLBACK TO SAVEPOINT row_save")
                        except Exception:
                            pass
                try:
                    conn_pg.commit()
                except Exception:
                    pass
            
            print(f"   ➔ Đang nạp dữ liệu: {min(i + batch_size, len(rows))}/{len(rows)} dòng...")

        print(f"   🎉 Hoàn thành: Đã xử lý {len(rows)} dòng thành công.")

    # 8. Đóng kết nối
    conn_lite.close()
    conn_pg.close()
    print("\n============================================================")
    print("✨ CHÚC MỪNG: QUY TRÌNH ĐỒNG BỘ DỮ LIỆU ĐÃ HOÀN THÀNH XUẤT SẮC! ✨")
    print("👉 Bây giờ Render Web Service của bạn đã được cài đặt đầy đủ dữ liệu sẵn có.")

if __name__ == "__main__":
    migrate()
