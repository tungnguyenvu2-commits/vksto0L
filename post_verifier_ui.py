import os
import sqlite3
import sys
from flask import Flask, render_template_string, jsonify, request
import requests
from dotenv import load_dotenv

# Đảm bảo in tiếng Việt chuẩn trên Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Tải biến môi trường
load_dotenv()

# Tự động chuyển hướng kết nối sang PostgreSQL nếu chạy trên Render (Deploy)
is_deployed = os.getenv("RENDER") or os.getenv("GITHUB_ACTIONS") or os.getenv("DEPLOYMENT_ENV")
if os.getenv("DATABASE_URL") and is_deployed:
    import psycopg2
    import psycopg2.extras
    
    class PGConnWrapper:
        def __init__(self, pg_conn):
            self._conn = pg_conn
            self.row_factory = None
            
        def cursor(self):
            if self.row_factory is not None:
                cursor = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            else:
                cursor = self._conn.cursor()
            
            class PGCursorWrapper:
                def __init__(self, pg_cursor):
                    self._cursor = pg_cursor
                    
                def execute(self, sql, params=None):
                    if params:
                        sql = sql.replace("?", "%s")
                    
                    # Chuyển đổi cú pháp INSERT OR REPLACE / INSERT OR IGNORE sang PostgreSQL
                    if "insert or ignore" in sql.lower() or "insert or replace" in sql.lower():
                        sql = sql.replace("INSERT OR IGNORE", "INSERT").replace("insert or ignore", "insert")
                        sql = sql.replace("INSERT OR REPLACE", "INSERT").replace("insert or replace", "insert")
                        
                        # Thêm điều kiện ON CONFLICT cho từng bảng
                        if "rss_sources" in sql:
                            sql += " ON CONFLICT (rss_url) DO NOTHING"
                        elif "raw_articles" in sql:
                            sql += " ON CONFLICT (url) DO NOTHING"
                        elif "classified_articles" in sql:
                            sql += " ON CONFLICT (raw_article_id) DO NOTHING"
                        elif "matched_cases" in sql:
                            sql += " ON CONFLICT (raw_article_id) DO UPDATE SET match_reason = EXCLUDED.match_reason"
                        elif "resolution_keywords" in sql:
                            sql += " ON CONFLICT (keyword) DO NOTHING"
                        elif "vks_settings" in sql:
                            sql += " ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
                    
                    # Chuyển đổi kiểu tự tăng INTEGER PRIMARY KEY AUTOINCREMENT
                    sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
                    sql = sql.replace("integer primary key autoincrement", "serial primary key")
                    
                    # Chuyển đổi các hàm datetime
                    sql = sql.replace("datetime('now')", "NOW()").replace("DATETIME('now')", "NOW()")
                    
                    if params:
                        self._cursor.execute(sql, params)
                    else:
                        self._cursor.execute(sql)
                        
                def fetchone(self):
                    res = self._cursor.fetchone()
                    if res is None:
                        return None
                    if isinstance(res, dict):
                        class DictRowWrapper(dict):
                            def __getitem__(self, item):
                                if isinstance(item, int):
                                    return list(self.values())[item]
                                return super().__getitem__(item)
                        return DictRowWrapper(res)
                    return res
                    
                def fetchall(self):
                    res = self._cursor.fetchall()
                    if res and isinstance(res[0], dict):
                        class DictRowWrapper(dict):
                            def __getitem__(self, item):
                                if isinstance(item, int):
                                    return list(self.values())[item]
                                return super().__getitem__(item)
                        return [DictRowWrapper(r) for r in res]
                    return res
                    
                def __getattr__(self, name):
                    return getattr(self._cursor, name)
                    
            return PGCursorWrapper(cursor)
            
        def commit(self):
            self._conn.commit()
            
        def close(self):
            self._conn.close()
            
        def __getattr__(self, name):
            return getattr(self._conn, name)

    original_sqlite_connect = sqlite3.connect
    def custom_connect(database, *args, **kwargs):
        if database == "crawler_data.db":
            pg_conn = psycopg2.connect(os.getenv("DATABASE_URL"))
            return PGConnWrapper(pg_conn)
        return original_sqlite_connect(database, *args, **kwargs)
    sqlite3.connect = custom_connect

app = Flask(__name__)
DB_FILE = "crawler_data.db"

# Khai báo 12 Lĩnh Vực Bảo Vệ theo Nghị quyết số 205/2025/QH15
DOMAINS = {
    1: "Nhóm dễ bị tổn thương: Trẻ em",
    2: "Nhóm dễ bị tổn thương: Người cao tuổi",
    3: "Nhóm dễ bị tổn thương: Người khuyết tật",
    4: "Nhóm dễ bị tổn thương: Phụ nữ mang thai / Nuôi con dưới 36 tháng",
    5: "Nhóm dễ bị tổn thương: Dân tộc thiểu số vùng ĐBKK",
    6: "Nhóm dễ bị tổn thương: Người khó khăn nhận thức / Mất năng lực hành vi",
    7: "Lợi ích công: Đầu tư công",
    8: "Lợi ích công: Tài sản công, Đất đai",
    9: "Lợi ích công: Môi trường, Hệ sinh thái",
    10: "Lợi ích công: Di sản văn hóa",
    11: "Lợi ích công: An toàn thực phẩm, Dược phẩm",
    12: "Lợi ích công: Bảo vệ quyền lợi người tiêu dùng"
}

def init_settings_table():
    """Khởi tạo bảng cấu hình bổ sung nếu chưa có"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vks_settings (
            key TEXT UNIQUE NOT NULL,
            value TEXT
        )
    ''')
    conn.commit()
    conn.close()

def upgrade_db_schema():
    """Tự động thêm các cột mới như telegram_sent vào bảng classified_articles nếu chưa có"""
    init_settings_table()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        # Kiểm tra xem cột telegram_sent đã tồn tại hay chưa
        cursor.execute("SELECT telegram_sent FROM classified_articles LIMIT 1")
    except Exception:
        # Nếu chưa tồn tại, tiến hành thêm cột
        try:
            cursor.execute("ALTER TABLE classified_articles ADD COLUMN telegram_sent INTEGER DEFAULT 0")
            conn.commit()
            print("✅ Đã tự động bổ sung cột 'telegram_sent' vào bảng classified_articles.")
        except Exception as e:
            print(f"⚠️ Lỗi khi thêm cột 'telegram_sent': {e}")
            conn.rollback()
    conn.close()

# Thực hiện nâng cấp DB schema ngay khi khởi chạy ứng dụng
upgrade_db_schema()

def get_setting(key, default=""):
    """Lấy cấu hình ưu tiên từ CSDL, nếu không có lấy từ file .env"""
    init_settings_table()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM vks_settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0]
    
    # Fallback to .env
    if key == "TELEGRAM_BOT":
        return os.getenv("TELEGRAM_BOT", default)
    elif key == "TELEGRAM_CHAT_ID":
        return os.getenv("TELEGRAM_CHAT_ID", default)
    return default

def save_setting(key, value):
    """Lưu cấu hình vào CSDL"""
    init_settings_table()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO vks_settings (key, value)
        VALUES (?, ?)
    ''', (key, value))
    conn.commit()
    conn.close()

# Giao diện chính (HTML5 + CSS HSL + Vanilla JS) nhúng trực tiếp dạng Single Page App
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VKS BOT - NVTung-VKSKV4-HaNoi</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: hsl(222, 47%, 10%);
            --card-bg: hsl(223, 47%, 14%);
            --card-border: rgba(255, 255, 255, 0.06);
            --text-main: hsl(210, 40%, 98%);
            --text-muted: hsl(215, 20%, 65%);
            --primary: linear-gradient(135deg, #6366f1, #a855f7);
            --primary-solid: #6366f1;
            --success: #10b981;
            --success-glow: rgba(16, 185, 129, 0.15);
            --danger: #ef4444;
            --danger-glow: rgba(239, 68, 68, 0.15);
            --warning: #f59e0b;
            --warning-glow: rgba(245, 158, 11, 0.15);
            --info: #3b82f6;
            --info-glow: rgba(59, 130, 246, 0.15);
            --font-family: 'Outfit', sans-serif;
            --transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            background-color: var(--bg-color);
            color: var(--text-main);
            font-family: var(--font-family);
            min-height: 100vh;
            padding: 2rem;
            line-height: 1.6;
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
            padding-bottom: 1.5rem;
            border-bottom: 1px solid var(--card-border);
        }

        .logo-section h1 {
            font-size: 1.8rem;
            font-weight: 700;
            background: var(--primary);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: -0.5px;
        }

        .logo-section p {
            color: var(--text-muted);
            font-size: 0.9rem;
            margin-top: 2px;
        }

        .branding-badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: linear-gradient(135deg, rgba(99, 102, 241, 0.2), rgba(168, 85, 247, 0.2));
            border: 1px solid rgba(168, 85, 247, 0.5);
            border-radius: 20px;
            padding: 4px 14px;
            font-size: 0.85rem;
            font-weight: 700;
            color: #d8b4fe;
            box-shadow: 0 4px 12px rgba(168, 85, 247, 0.15);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            animation: pulse-glow 2s infinite alternate;
            vertical-align: middle;
        }

        .badge-icon {
            font-size: 0.95rem;
        }

        @keyframes pulse-glow {
            from {
                border-color: rgba(168, 85, 247, 0.5);
                box-shadow: 0 4px 12px rgba(168, 85, 247, 0.15);
            }
            to {
                border-color: rgba(99, 102, 241, 0.9);
                box-shadow: 0 4px 20px rgba(99, 102, 241, 0.4);
            }
        }

        .antigravity-badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: linear-gradient(135deg, rgba(6, 182, 212, 0.15), rgba(59, 130, 246, 0.15));
            border: 1px solid rgba(6, 182, 212, 0.4);
            border-radius: 20px;
            padding: 4px 14px;
            font-size: 0.85rem;
            font-weight: 700;
            color: #a5f3fc;
            box-shadow: 0 4px 12px rgba(6, 182, 212, 0.15);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            animation: float-gravity 3s ease-in-out infinite alternate;
            vertical-align: middle;
        }

        .antigravity-icon {
            display: inline-block;
            font-size: 0.95rem;
            animation: rotate-planet 8s linear infinite;
        }

        @keyframes float-gravity {
            from {
                transform: translateY(0px);
                box-shadow: 0 4px 12px rgba(6, 182, 212, 0.15);
            }
            to {
                transform: translateY(-5px);
                box-shadow: 0 10px 20px rgba(6, 182, 212, 0.35);
            }
        }

        @keyframes rotate-planet {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
        }

        /* Thống kê Tổng quan (Stats Dashboard) */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }

        .stat-card {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 1.2rem;
            display: flex;
            flex-direction: column;
            position: relative;
            overflow: hidden;
            transition: var(--transition);
        }

        .stat-card:hover {
            transform: translateY(-5px);
            border-color: rgba(255, 255, 255, 0.12);
            box-shadow: 0 10px 20px rgba(0, 0, 0, 0.2);
        }

        .stat-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 4px;
            height: 100%;
            background: var(--primary-solid);
        }

        .stat-card.pending::before { background: var(--warning); }
        .stat-card.approved::before { background: var(--success); }
        .stat-card.telegram::before { background: var(--info); }
        .stat-card.rejected::before { background: var(--danger); }

        .stat-title {
            color: var(--text-muted);
            font-size: 0.8rem;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .stat-value {
            font-size: 1.8rem;
            font-weight: 700;
            margin-top: 0.5rem;
            color: var(--text-main);
        }

        /* Giao diện chính */
        .main-layout {
            display: grid;
            grid-template-columns: 1fr 320px;
            gap: 2rem;
        }

        @media (max-width: 1200px) {
            .main-layout {
                grid-template-columns: 1fr;
            }
        }

        .content-panel {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 20px;
            padding: 2rem;
            box-shadow: 0 8px 30px rgba(0, 0, 0, 0.15);
            overflow: hidden;
        }

        .panel-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.5rem;
            flex-wrap: wrap;
            gap: 1rem;
        }

        .tabs {
            display: flex;
            gap: 0.4rem;
            background: rgba(0, 0, 0, 0.25);
            padding: 4px;
            border-radius: 12px;
            border: 1px solid var(--card-border);
            flex-wrap: wrap;
        }

        .tab-btn {
            background: transparent;
            border: none;
            color: var(--text-muted);
            padding: 8px 14px;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 500;
            font-size: 0.88rem;
            font-family: var(--font-family);
            transition: var(--transition);
        }

        .tab-btn:hover {
            color: var(--text-main);
        }

        .tab-btn.active {
            background: var(--primary);
            color: var(--text-main);
            box-shadow: 0 4px 12px rgba(168, 85, 247, 0.25);
        }

        .search-box {
            position: relative;
        }

        .search-box input {
            background: rgba(0, 0, 0, 0.25);
            border: 1px solid var(--card-border);
            color: var(--text-main);
            padding: 10px 16px;
            border-radius: 10px;
            font-family: var(--font-family);
            font-size: 0.9rem;
            width: 220px;
            transition: var(--transition);
        }

        .search-box input:focus {
            outline: none;
            border-color: var(--primary-solid);
            box-shadow: 0 0 10px rgba(99, 102, 241, 0.2);
        }

        /* Dropdown sắp xếp */
        .sort-box {
            position: relative;
        }

        .sort-select {
            background: rgba(0, 0, 0, 0.25);
            border: 1px solid var(--card-border);
            color: var(--text-main);
            padding: 10px 32px 10px 14px;
            border-radius: 10px;
            font-family: var(--font-family);
            font-size: 0.88rem;
            cursor: pointer;
            transition: var(--transition);
            appearance: none;
            -webkit-appearance: none;
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%238892a4' d='M6 8L1 3h10z'/%3E%3C/svg%3E");
            background-repeat: no-repeat;
            background-position: right 12px center;
        }

        .sort-select:focus {
            outline: none;
            border-color: var(--primary-solid);
            box-shadow: 0 0 10px rgba(99, 102, 241, 0.2);
        }

        .sort-select option {
            background: hsl(223, 47%, 14%);
            color: var(--text-main);
        }

        /* Danh sách bài viết */
        .articles-list {
            display: flex;
            flex-direction: column;
            gap: 1.2rem;
        }

        .article-card {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--card-border);
            border-radius: 14px;
            padding: 1.5rem;
            transition: var(--transition);
            animation: fadeIn 0.4s ease;
        }

        .article-card:hover {
            border-color: rgba(255, 255, 255, 0.1);
            background: rgba(255, 255, 255, 0.03);
        }

        .article-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 1rem;
            margin-bottom: 0.8rem;
        }

        .article-source {
            font-size: 0.8rem;
            font-weight: 600;
            background: rgba(99, 102, 241, 0.12);
            color: #818cf8;
            padding: 4px 10px;
            border-radius: 6px;
            text-transform: uppercase;
        }

        .article-score {
            font-size: 0.8rem;
            font-weight: 700;
            padding: 4px 10px;
            border-radius: 6px;
        }

        .score-high { background: var(--success-glow); color: var(--success); }
        .score-medium { background: var(--warning-glow); color: var(--warning); }
        .score-low { background: var(--danger-glow); color: var(--danger); }

        .article-title {
            font-size: 1.1rem;
            font-weight: 600;
            color: var(--text-main);
            margin-bottom: 0.8rem;
            line-height: 1.4;
        }

        .article-title a {
            color: inherit;
            text-decoration: none;
            transition: var(--transition);
        }

        .article-title a:hover {
            color: #a855f7;
            text-decoration: underline;
        }

        .article-summary-editor {
            width: 100%;
            background: rgba(0, 0, 0, 0.3);
            border: 1px solid var(--card-border);
            color: var(--text-muted);
            border-radius: 8px;
            padding: 10px;
            font-family: var(--font-family);
            font-size: 0.88rem;
            resize: vertical;
            min-height: 70px;
            margin-bottom: 1rem;
            transition: var(--transition);
        }

        .article-summary-editor:focus {
            outline: none;
            border-color: var(--primary-solid);
            color: var(--text-main);
        }

        .article-meta-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            background: rgba(0, 0, 0, 0.15);
            padding: 1rem;
            border-radius: 10px;
            border: 1px solid rgba(255, 255, 255, 0.03);
            margin-bottom: 1rem;
            font-size: 0.85rem;
        }

        .meta-item strong {
            display: block;
            color: var(--text-muted);
            font-weight: 500;
            margin-bottom: 2px;
        }

        .meta-item span {
            color: var(--text-main);
            font-weight: 500;
        }

        /* Nút Hành động */
        .actions-bar {
            display: flex;
            justify-content: flex-end;
            gap: 0.8rem;
            flex-wrap: wrap;
        }

        .btn {
            border: none;
            padding: 8px 16px;
            border-radius: 8px;
            font-weight: 600;
            font-family: var(--font-family);
            font-size: 0.85rem;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            transition: var(--transition);
        }

        .btn-select {
            background: var(--success);
            color: #ffffff;
            box-shadow: 0 4px 10px rgba(16, 185, 129, 0.2);
        }

        .btn-select:hover {
            background: #059669;
            transform: translateY(-2px);
        }

        .btn-reject {
            background: var(--danger);
            color: #ffffff;
            box-shadow: 0 4px 10px rgba(239, 68, 68, 0.2);
        }

        .btn-reject:hover {
            background: #dc2626;
            transform: translateY(-2px);
        }

        .btn-tele {
            background: var(--info);
            color: #ffffff;
            box-shadow: 0 4px 10px rgba(59, 130, 246, 0.2);
        }

        .btn-tele:hover {
            background: #2563eb;
            transform: translateY(-2px);
        }

        .btn-muted {
            background: rgba(255, 255, 255, 0.08);
            color: var(--text-muted);
        }

        .btn-muted:hover {
            background: rgba(255, 255, 255, 0.12);
            color: var(--text-main);
        }

        /* Sidebar Cấu hình */
        .sidebar {
            display: flex;
            flex-direction: column;
            gap: 1.5rem;
        }

        .config-panel {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 20px;
            padding: 1.5rem;
            box-shadow: 0 8px 30px rgba(0, 0, 0, 0.15);
        }

        .config-panel h3 {
            font-size: 1.1rem;
            font-weight: 600;
            margin-bottom: 1rem;
            background: var(--primary);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            border-bottom: 1px solid var(--card-border);
            padding-bottom: 0.5rem;
        }

        .form-group {
            margin-bottom: 1rem;
        }

        .form-group label {
            display: block;
            font-size: 0.8rem;
            color: var(--text-muted);
            margin-bottom: 6px;
            font-weight: 500;
        }

        .form-group input {
            width: 100%;
            background: rgba(0, 0, 0, 0.25);
            border: 1px solid var(--card-border);
            color: var(--text-main);
            padding: 8px 12px;
            border-radius: 8px;
            font-family: var(--font-family);
            font-size: 0.85rem;
            transition: var(--transition);
        }

        .form-group input:focus {
            outline: none;
            border-color: var(--primary-solid);
        }

        /* Custom Toast notification */
        #toast-container {
            position: fixed;
            bottom: 20px;
            right: 20px;
            z-index: 1000;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }

        .toast {
            background: hsl(223, 47%, 18%);
            border: 1px solid var(--card-border);
            border-left: 4px solid var(--primary-solid);
            color: var(--text-main);
            padding: 12px 20px;
            border-radius: 8px;
            box-shadow: 0 10px 20px rgba(0, 0, 0, 0.3);
            font-size: 0.88rem;
            font-weight: 500;
            min-width: 250px;
            max-width: 350px;
            animation: slideIn 0.3s ease forwards;
        }

        .toast.success { border-left-color: var(--success); }
        .toast.danger { border-left-color: var(--danger); }
        .toast.warning { border-left-color: var(--warning); }

        @keyframes slideIn {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        /* Empty State */
        .empty-state {
            text-align: center;
            padding: 3rem;
            color: var(--text-muted);
        }

        .empty-state svg {
            width: 48px;
            height: 48px;
            stroke: var(--text-muted);
            margin-bottom: 1rem;
            opacity: 0.5;
        }

        .article-card.selected {
            border-color: var(--primary-solid) !important;
            background: rgba(99, 102, 241, 0.06) !important;
            box-shadow: 0 0 15px rgba(99, 102, 241, 0.15) !important;
        }

        /* ---------------------------------------------------- */
        /* GIAO DIỆN BẢNG EXCEL HIỆN ĐẠI (Telegram Sent view)   */
        /* ---------------------------------------------------- */
        .excel-table-container {
            width: 100%;
            overflow-x: auto;
            border-radius: 14px;
            border: 1px solid var(--card-border);
            background: rgba(0, 0, 0, 0.25);
            box-shadow: 0 8px 30px rgba(0, 0, 0, 0.3);
            margin-bottom: 1.5rem;
        }

        .excel-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.88rem;
            text-align: left;
            min-width: 1000px;
        }

        .excel-table th {
            background: linear-gradient(180deg, hsl(223, 47%, 16%), hsl(223, 47%, 12%));
            color: var(--text-main);
            font-weight: 600;
            padding: 14px 16px;
            border-bottom: 2px solid rgba(255, 255, 255, 0.1);
            border-right: 1px solid rgba(255, 255, 255, 0.05);
            text-transform: uppercase;
            font-size: 0.78rem;
            letter-spacing: 0.5px;
            position: sticky;
            top: 0;
            z-index: 5;
        }

        .excel-table td {
            padding: 14px 16px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            border-right: 1px solid rgba(255, 255, 255, 0.05);
            color: var(--text-muted);
            vertical-align: middle;
            transition: var(--transition);
        }

        .excel-table tr:nth-child(even) {
            background: rgba(255, 255, 255, 0.015);
        }

        .excel-table tr:hover {
            background: rgba(99, 102, 241, 0.06);
        }

        .excel-table tr:hover td {
            color: var(--text-main);
        }

        .excel-table tr.selected {
            background: rgba(99, 102, 241, 0.1) !important;
            border-left: 3px solid var(--primary-solid);
        }

        .excel-table th:last-child, .excel-table td:last-child {
            border-right: none;
        }

        .excel-title-cell {
            font-weight: 500;
            color: var(--text-main);
        }

        .excel-title-cell a {
            color: inherit;
            text-decoration: none;
            transition: var(--transition);
        }

        .excel-title-cell a:hover {
            color: #a855f7;
            text-decoration: underline;
        }

        .excel-summary-cell {
            font-size: 0.85rem;
            color: var(--text-muted);
            transition: var(--transition);
            border: 1px dashed rgba(255, 255, 255, 0.15);
            border-radius: 6px;
            background: rgba(0, 0, 0, 0.15);
        }

        .excel-summary-cell:focus {
            background: rgba(0, 0, 0, 0.5);
            color: var(--text-main);
            border: 1px solid var(--primary-solid);
            outline: none;
            box-shadow: 0 0 8px rgba(99, 102, 241, 0.3);
        }

        .status-sent-badge {
            background: rgba(16, 185, 129, 0.15);
            color: var(--success);
            border: 1px solid rgba(16, 185, 129, 0.3);
            border-radius: 6px;
            padding: 4px 10px;
            font-size: 0.75rem;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }

        /* Scrollbars for Excel Table */
        .excel-table-container::-webkit-scrollbar {
            height: 8px;
            width: 8px;
        }
        .excel-table-container::-webkit-scrollbar-track {
            background: rgba(0, 0, 0, 0.1);
            border-radius: 10px;
        }
        .excel-table-container::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.15);
            border-radius: 10px;
        }
        .excel-table-container::-webkit-scrollbar-thumb:hover {
            background: rgba(255, 255, 255, 0.3);
        }
    </style>
</head>
<body>
    <header>
        <div class="logo-section">
            <h1 style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
                <span>🏛️ HẬU KIỂM VKS BOT</span>
                <span class="branding-badge">
                    <span class="badge-icon">👑</span>
                    <span class="badge-text">1 sản phẩm của NVTung-VKSkv4-HaNoi</span>
                </span>
                <span class="antigravity-badge">
                    <span class="antigravity-icon">🪐</span>
                    <span class="antigravity-text">Powered by Gemini-Antigravity</span>
                </span>
            </h1>
            <p>Hệ thống phê duyệt báo cáo vi phạm theo Nghị quyết số 205/2025/QH15 | 1 sản phẩm của NVTung-VKSkv4-HaNoi</p>
        </div>
        <div class="header-actions">
            <span id="network-badge" class="article-source" style="background: rgba(16, 185, 129, 0.12); color: var(--success);">ONLINE</span>
        </div>
    </header>

    <!-- Thống kê Dashboard -->
    <div class="stats-grid">
        <div class="stat-card pending">
            <span class="stat-title">Chờ Hậu Kiểm (Pending)</span>
            <div id="stat-pending-val" class="stat-value">0</div>
        </div>
        <div class="stat-card approved">
            <span class="stat-title">Đã Chấp Nhận (Selected)</span>
            <div id="stat-approved-val" class="stat-value">0</div>
        </div>
        <div class="stat-card telegram">
            <span class="stat-title">Đã Gửi Telegram (Sent)</span>
            <div id="stat-telegram-val" class="stat-value">0</div>
        </div>
        <div class="stat-card rejected">
            <span class="stat-title">Đã Từ Chối (Rejected)</span>
            <div id="stat-rejected-val" class="stat-value">0</div>
        </div>
        <div class="stat-card">
            <span class="stat-title">Tổng Tin Khớp AI</span>
            <div id="stat-total-val" class="stat-value">0</div>
        </div>
    </div>

    <!-- Bố cục chính -->
    <div class="main-layout">
        <!-- Panel Danh sách -->
        <div class="content-panel">
            <div class="panel-header">
                <div class="tabs">
                    <button class="tab-btn active" onclick="switchTab('pending')">⏳ Chờ xử lý</button>
                    <button class="tab-btn" onclick="switchTab('approved')">✅ Được chọn</button>
                    <button class="tab-btn" onclick="switchTab('telegram')">✈️ Đã gửi Telegram</button>
                    <button class="tab-btn" onclick="switchTab('rejected')">❌ Bị loại bỏ</button>
                </div>
                <div class="search-box">
                    <input type="text" id="search-input" placeholder="Tìm kiếm tiêu đề hoặc nguồn..." oninput="handleSearch()">
                </div>
                <div class="sort-box">
                    <select id="sort-select" class="sort-select" onchange="handleSort()">
                        <option value="date_desc">📅 Mới nhất trước</option>
                        <option value="date_asc">📅 Cũ nhất trước</option>
                        <option value="score_desc">🔢 Điểm cao nhất</option>
                        <option value="pub_desc">📰 Ngày đăng bài</option>
                    </select>
                </div>
            </div>

            <!-- Thanh hành động hàng loạt (Batch Action Bar) -->
            <div id="batch-action-bar" style="display: none; position: sticky; top: 0; z-index: 100; background: hsl(223, 47%, 16%); border: 1px solid var(--primary-solid); border-radius: 12px; padding: 12px 20px; margin-bottom: 1.5rem; justify-content: space-between; align-items: center; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4); animation: slideIn 0.3s ease; flex-wrap: wrap; gap: 10px;">
                <div style="display: flex; align-items: center; gap: 12px;">
                    <input type="checkbox" id="select-all-checkbox" onchange="toggleSelectAll()" style="width: 18px; height: 18px; cursor: pointer; accent-color: var(--primary-solid);">
                    <label for="select-all-checkbox" style="font-weight: 600; font-size: 0.9rem; cursor: pointer; color: var(--text-main);">Chọn tất cả</label>
                    <span id="selected-count-badge" class="article-source" style="background: rgba(168, 85, 247, 0.2); color: #c084fc;">Đã chọn 0 bài</span>
                </div>
                <div id="batch-buttons" style="display: flex; gap: 8px;">
                    <!-- Sẽ được điền động tùy theo Tab bằng JS -->
                </div>
            </div>

            <!-- List tin bài -->
            <div id="articles-container" class="articles-list">
                <!-- Nội dung được điền tự động bằng JavaScript -->
            </div>
        </div>

        <!-- Sidebar Cấu hình -->
        <div class="sidebar">
            <div class="config-panel">
                <h3>⚙️ Cấu Hình Telegram</h3>
                <div class="form-group">
                    <label for="config-bot-token">BOT TOKEN</label>
                    <input type="password" id="config-bot-token" placeholder="8656158264:AAHzW..." />
                </div>
                <div class="form-group">
                    <label for="config-chat-id">TELEGRAM CHAT ID</label>
                    <input type="text" id="config-chat-id" placeholder="-100xxxxxxx" />
                </div>
                <button class="btn btn-select" style="width: 100%; justify-content: center;" onclick="saveConfig()">Lưu cấu hình</button>
            </div>
            
            <div class="config-panel" style="background: linear-gradient(135deg, hsl(223, 47%, 14%), hsl(223, 47%, 11%)); border: 1px solid var(--primary-solid);">
                <h3 style="background: var(--primary); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">📖 Hướng Dẫn Hậu Kiểm</h3>
                <p style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 10px;">
                    Quy trình duyệt tin bài đảm bảo tính minh bạch trước khi phát sóng báo cáo lên Telegram:
                </p>
                <ul style="font-size: 0.8rem; color: var(--text-muted); padding-left: 15px; display: flex; flex-direction: column; gap: 8px;">
                    <li><strong>Duyệt (Select)</strong>: Đánh dấu tin bài chính xác là vi phạm, sẵn sàng phát đi.</li>
                    <li><strong>Bỏ qua (Reject)</strong>: Lọc bỏ tin rác hoặc sai sót trong phán quyết của AI.</li>
                    <li><strong>Hậu kiểm</strong>: Bạn có thể sửa trực tiếp Nội dung trích dẫn (Summary) trước khi duyệt.</li>
                    <li><strong>Bảng Excel</strong>: Mục đã gửi Telegram thiết kế dạng bảng Excel hiện đại giúp bạn dễ dàng theo dõi trực quan và chỉnh sửa nhanh tóm tắt vụ việc.</li>
                </ul>
            </div>
        </div>
    </div>

    <!-- Container Thông Báo -->
    <div id="toast-container"></div>

    <script>
        let currentTab = 'pending';
        let currentSort = 'date_desc';
        let searchQuery = '';
        let articlesData = [];
        let selectedIds = new Set();

        // Khởi chạy khi load trang
        document.addEventListener("DOMContentLoaded", () => {
            loadConfig();
            fetchStats();
            fetchArticles();
        });

        // Hàm Toast Alert tự dựng sang xịn mịn
        function showToast(message, type = 'success') {
            const container = document.getElementById("toast-container");
            const toast = document.createElement("div");
            toast.className = `toast ${type}`;
            toast.innerText = message;
            container.appendChild(toast);
            
            setTimeout(() => {
                toast.style.animation = "slideIn 0.3s ease reverse forwards";
                setTimeout(() => { toast.remove(); }, 300);
            }, 3000);
        }

        // Tải cấu hình Telegram từ API
        async function loadConfig() {
            try {
                const res = await fetch('/api/config');
                const config = await res.json();
                document.getElementById("config-bot-token").value = config.TELEGRAM_BOT || '';
                document.getElementById("config-chat-id").value = config.TELEGRAM_CHAT_ID || '';
            } catch (err) {
                showToast("Lỗi tải cấu hình Telegram", "danger");
            }
        }

        // Lưu cấu hình Telegram
        async function saveConfig() {
            const botToken = document.getElementById("config-bot-token").value.trim();
            const chatId = document.getElementById("config-chat-id").value.trim();
            
            try {
                const res = await fetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ TELEGRAM_BOT: botToken, TELEGRAM_CHAT_ID: chatId })
                });
                const result = await res.json();
                if (result.success) {
                    showToast("Đã lưu cấu hình Telegram thành công!");
                } else {
                    showToast("Không thể lưu cấu hình", "danger");
                }
            } catch (err) {
                showToast("Lỗi kết nối lưu cấu hình", "danger");
            }
        }

        // Tải số liệu thống kê Dashboard
        async function fetchStats() {
            try {
                const res = await fetch('/api/stats');
                const stats = await res.json();
                document.getElementById("stat-pending-val").innerText = stats.pending || 0;
                document.getElementById("stat-approved-val").innerText = stats.approved || 0;
                document.getElementById("stat-telegram-val").innerText = stats.telegram_sent || 0;
                document.getElementById("stat-rejected-val").innerText = stats.rejected || 0;
                document.getElementById("stat-total-val").innerText = stats.total || 0;
            } catch (err) {
                console.error("Lỗi fetchStats", err);
            }
        }

        // Thay đổi Tab
        function switchTab(tab) {
            currentTab = tab;
            selectedIds.clear();
            updateBatchActionBar();
            document.querySelectorAll(".tab-btn").forEach(btn => btn.classList.remove("active"));
            
            let activeIdx = 0;
            if (tab === 'approved') activeIdx = 1;
            if (tab === 'telegram') activeIdx = 2;
            if (tab === 'rejected') activeIdx = 3;
            document.querySelectorAll(".tab-btn")[activeIdx].classList.add("active");
            
            fetchArticles();
        }

        // Xử lý Tìm Kiếm
        function handleSearch() {
            searchQuery = document.getElementById("search-input").value.toLowerCase();
            selectedIds.clear();
            updateBatchActionBar();
            renderArticles();
        }

        // Xử lý Sắp Xếp
        function handleSort() {
            currentSort = document.getElementById("sort-select").value;
            selectedIds.clear();
            updateBatchActionBar();
            fetchArticles();
        }

        // Tải danh sách tin bài
        async function fetchArticles() {
            const container = document.getElementById("articles-container");
            container.innerHTML = `<div class="empty-state">⏳ Đang tải dữ liệu...</div>`;
            selectedIds.clear();
            updateBatchActionBar();
            
            try {
                const res = await fetch(`/api/articles?status=${currentTab}&sort=${currentSort}`);
                articlesData = await res.json();
                renderArticles();
            } catch (err) {
                container.innerHTML = `<div class="empty-state" style="color: var(--danger);">❌ Lỗi tải danh sách bài viết</div>`;
            }
        }

        // Phân loại màu sắc điểm độ tin cậy
        function getScoreClass(score) {
            if (score >= 0.75) return 'score-high';
            if (score >= 0.4) return 'score-medium';
            return 'score-low';
        }

        // Render HTML các bài viết ra giao diện
        function renderArticles() {
            const container = document.getElementById("articles-container");
            container.innerHTML = "";

            const filtered = articlesData.filter(art => {
                const title = (art.title || '').toLowerCase();
                const source = (art.source_name || '').toLowerCase();
                return title.includes(searchQuery) || source.includes(searchQuery);
            });

            if (filtered.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <circle cx="12" cy="12" r="10"></circle>
                            <line x1="12" y1="8" x2="12" y2="12"></line>
                            <line x1="12" y1="16" x2="12.01" y2="16"></line>
                        </svg>
                        <p>Không tìm thấy tin bài nào khớp bộ lọc.</p>
                    </div>
                `;
                return;
            }

            // Nếu là Tab Telegram, render dạng bảng Excel cực hiện đại
            if (currentTab === 'telegram') {
                renderTelegramTable(filtered);
                return;
            }

            filtered.forEach(art => {
                const card = document.createElement("div");
                card.className = "article-card" + (selectedIds.has(art.id) ? " selected" : "");
                
                const scorePercent = Math.round(art.confidence_score * 100);
                const scoreClass = getScoreClass(art.confidence_score);

                // Tạo các nút hành động tương ứng với từng Tab
                let actionsHTML = '';
                if (currentTab === 'pending') {
                    actionsHTML = `
                        <button class="btn btn-select" onclick="evaluateArticle(${art.id}, 1)">👍 Chọn (Select)</button>
                        <button class="btn btn-reject" onclick="evaluateArticle(${art.id}, 0)">👎 Loại bỏ (Reject)</button>
                    `;
                } else if (currentTab === 'approved') {
                    actionsHTML = `
                        <button class="btn btn-tele" onclick="sendToTelegram(${art.id})">✈️ Gửi Telegram</button>
                        <button class="btn btn-muted" onclick="evaluateArticle(${art.id}, 0)">Hủy chọn (Reject)</button>
                    `;
                } else {
                    actionsHTML = `
                        <button class="btn btn-muted" onclick="evaluateArticle(${art.id}, 1)">Khôi phục duyệt (Select)</button>
                    `;
                }

                card.innerHTML = `
                    <div class="article-header">
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <input type="checkbox" class="article-select-checkbox" data-id="${art.id}" onchange="toggleSelectArticle(${art.id})" style="width: 18px; height: 18px; cursor: pointer; accent-color: var(--primary-solid);" ${selectedIds.has(art.id) ? 'checked' : ''}>
                            <span class="article-source">${art.source_name} (${art.source_type})</span>
                        </div>
                        <span class="article-score ${scoreClass}">Độ tin cậy: ${scorePercent}%</span>
                    </div>
                    
                    <h4 class="article-title">
                        <a href="${art.url}" target="_blank" title="Mở đường dẫn gốc">${art.title}</a>
                    </h4>
                    
                    <label style="display:block; font-size:0.75rem; color:var(--text-muted); margin-bottom:4px; font-weight:500;">TÓM TẮT & TRÍCH DẪN (CÓ THỂ SỬA TRỰC TIẾP)</label>
                    <textarea id="summary-${art.id}" class="article-summary-editor" placeholder="Nội dung tóm tắt...">${art.summary || ''}</textarea>
                    
                    <div class="article-meta-grid">
                        <div class="meta-item">
                            <strong>LĨNH VỰC BẢO VỆ (205)</strong>
                            <span>${art.domain_name || 'Không rõ'}</span>
                        </div>
                        <div class="meta-item">
                            <strong>LÝ DO CỦA AI</strong>
                            <span style="font-size:0.8rem; color:#f59e0b;">${art.match_reason || 'Không xác định'}</span>
                        </div>
                        <div class="meta-item">
                            <strong>MÔ HÌNH PHÂN LOẠI</strong>
                            <span style="font-size:0.8rem; color:#818cf8;">${art.classifier_model}</span>
                        </div>
                    </div>
                    
                    <div class="actions-bar">
                        ${actionsHTML}
                    </div>
                `;
                container.appendChild(card);
            });
            updateBatchActionBar();
        }

        // Render danh sách Đã Gửi Telegram dạng bảng Excel chuyên nghiệp hiện đại
        function renderTelegramTable(filtered) {
            const container = document.getElementById("articles-container");
            
            const tableWrapper = document.createElement("div");
            tableWrapper.className = "excel-table-container";

            const table = document.createElement("table");
            table.className = "excel-table";

            // Headers
            table.innerHTML = `
                <thead>
                    <tr>
                        <th style="width: 50px; text-align: center;">
                            <input type="checkbox" id="excel-select-all" onchange="toggleSelectAll()" style="width: 16px; height: 16px; cursor: pointer; accent-color: var(--primary-solid);">
                        </th>
                        <th style="width: 50px; text-align: center;">STT</th>
                        <th style="width: 140px;">Nguồn Báo</th>
                        <th>Tiêu đề Vụ việc</th>
                        <th style="width: 280px;">Tóm tắt sự kiện (Double click để sửa)</th>
                        <th style="width: 180px;">Lĩnh vực 205</th>
                        <th style="width: 100px; text-align: center;">Tin cậy</th>
                        <th style="width: 120px; text-align: center;">Gửi Tele</th>
                        <th style="width: 150px; text-align: center;">Thao tác</th>
                    </tr>
                </thead>
                <tbody id="excel-table-body">
                </tbody>
            `;

            tableWrapper.appendChild(table);
            container.appendChild(tableWrapper);

            const tbody = table.querySelector("#excel-table-body");

            filtered.forEach((art, index) => {
                const tr = document.createElement("tr");
                tr.className = selectedIds.has(art.id) ? "selected" : "";
                
                const scorePercent = Math.round(art.confidence_score * 100);
                const scoreClass = getScoreClass(art.confidence_score);

                tr.innerHTML = `
                    <td style="text-align: center;">
                        <input type="checkbox" class="excel-select-checkbox" data-id="${art.id}" onchange="toggleSelectArticle(${art.id})" style="width: 16px; height: 16px; cursor: pointer; accent-color: var(--primary-solid);" ${selectedIds.has(art.id) ? 'checked' : ''}>
                    </td>
                    <td style="text-align: center; font-weight: 600; color: var(--text-muted);">${index + 1}</td>
                    <td>
                        <span class="article-source" style="font-size: 0.72rem; padding: 2px 6px; white-space: nowrap;">${art.source_name}</span>
                        <div style="font-size: 0.7rem; color: var(--text-muted); margin-top: 3px;">${art.source_type}</div>
                    </td>
                    <td class="excel-title-cell">
                        <a href="${art.url}" target="_blank" title="Xem bài viết gốc">${art.title}</a>
                        <div style="font-size: 0.72rem; color: var(--warning); margin-top: 4px; line-height: 1.3;" title="AI Match Reason">
                            🔍 <i>AI: ${art.match_reason || 'Khớp từ khóa'}</i>
                        </div>
                    </td>
                    <td>
                        <div class="excel-summary-cell" contenteditable="true" 
                             onblur="updateExcelSummary(${art.id}, this)"
                             title="Double click để sửa tóm tắt này trực tiếp như trên Excel"
                             style="min-height: 40px; padding: 6px; outline: none; line-height: 1.4;">
                            ${art.summary || ''}
                        </div>
                    </td>
                    <td>
                        <span style="font-size: 0.8rem; font-weight: 500; color: #d8b4fe;">⚖️ ${art.domain_name}</span>
                    </td>
                    <td style="text-align: center;">
                        <span class="article-score ${scoreClass}" style="font-size: 0.75rem; padding: 2px 6px; border-radius: 4px;">${scorePercent}%</span>
                    </td>
                    <td style="text-align: center;">
                        <span class="status-sent-badge">✈️ Sent OK</span>
                    </td>
                    <td style="text-align: center;">
                        <div style="display: flex; gap: 6px; justify-content: center; align-items: center;">
                            <button class="btn btn-tele" onclick="sendToTelegram(${art.id})" style="padding: 4px 8px; font-size: 0.72rem;" title="Gửi lại Telegram để cập nhật">
                                🔄 Gửi lại
                            </button>
                            <button class="btn btn-muted" onclick="evaluateArticle(${art.id}, 0)" style="padding: 4px 8px; font-size: 0.72rem; background: var(--danger-glow); color: var(--danger);" title="Bỏ chọn và chuyển vào Bị loại bỏ">
                                🗑️ Hủy
                            </button>
                        </div>
                    </td>
                `;
                tbody.appendChild(tr);
            });

            updateBatchActionBar();
        }

        // Toggles single article selection
        function toggleSelectArticle(id) {
            const checkbox = document.querySelector(`.article-select-checkbox[data-id="${id}"], .excel-select-checkbox[data-id="${id}"]`);
            if (!checkbox) return;
            const container = checkbox.closest('.article-card, tr');
            
            if (checkbox.checked) {
                selectedIds.add(id);
                if (container) container.classList.add('selected');
            } else {
                selectedIds.delete(id);
                if (container) container.classList.remove('selected');
            }
            updateBatchActionBar();
        }

        // Toggles selection of all visible articles
        function toggleSelectAll() {
            const selectAllCheckbox = document.getElementById("select-all-checkbox") || document.getElementById("excel-select-all");
            const visibleCheckboxes = document.querySelectorAll(".article-select-checkbox, .excel-select-checkbox");
            
            visibleCheckboxes.forEach(cb => {
                const id = parseInt(cb.getAttribute("data-id"));
                const container = cb.closest('.article-card, tr');
                if (selectAllCheckbox.checked) {
                    selectedIds.add(id);
                    cb.checked = true;
                    if (container) container.classList.add('selected');
                } else {
                    selectedIds.delete(id);
                    cb.checked = false;
                    if (container) container.classList.remove('selected');
                }
            });
            updateBatchActionBar();
        }

        // Updates selected count and buttons in the batch action bar
        function updateBatchActionBar() {
            const bar = document.getElementById("batch-action-bar");
            const countBadge = document.getElementById("selected-count-badge");
            const selectAllCheckbox = document.getElementById("select-all-checkbox");
            const excelSelectAll = document.getElementById("excel-select-all");
            const batchButtons = document.getElementById("batch-buttons");
            
            const visibleCheckboxes = document.querySelectorAll(".article-select-checkbox, .excel-select-checkbox");
            const totalVisible = visibleCheckboxes.length;
            
            if (totalVisible === 0) {
                bar.style.display = "none";
                return;
            }
            
            bar.style.display = "flex";
            countBadge.innerText = `Đã chọn ${selectedIds.size} bài`;
            
            // Check if all visible checkboxes are checked
            let allChecked = totalVisible > 0;
            visibleCheckboxes.forEach(cb => {
                const id = parseInt(cb.getAttribute("data-id"));
                if (!selectedIds.has(id)) {
                    allChecked = false;
                }
            });
            
            if (selectAllCheckbox) selectAllCheckbox.checked = allChecked;
            if (excelSelectAll) excelSelectAll.checked = allChecked;
            
            // Update buttons dynamically based on tab and selection
            let buttonsHTML = '';
            if (selectedIds.size > 0) {
                if (currentTab === 'pending') {
                    buttonsHTML = `
                        <button class="btn btn-select" onclick="batchEvaluate(1)">👍 Duyệt ${selectedIds.size} bài</button>
                        <button class="btn btn-reject" onclick="batchEvaluate(0)">👎 Loại bỏ ${selectedIds.size} bài</button>
                    `;
                } else if (currentTab === 'approved') {
                    buttonsHTML = `
                        <button class="btn btn-tele" onclick="batchSendTelegram()">✈️ Gửi Telegram ${selectedIds.size} bài</button>
                        <button class="btn btn-reject" onclick="batchEvaluate(0)">👎 Hủy chọn ${selectedIds.size} bài</button>
                    `;
                } else if (currentTab === 'telegram') {
                    buttonsHTML = `
                        <button class="btn btn-tele" onclick="batchSendTelegram()">✈️ Gửi lại Tele ${selectedIds.size} bài</button>
                        <button class="btn btn-reject" onclick="batchEvaluate(0)" style="background: var(--danger); color: white;">👎 Loại bỏ ${selectedIds.size} bài</button>
                    `;
                } else {
                    buttonsHTML = `
                        <button class="btn btn-select" onclick="batchEvaluate(1)">👍 Khôi phục ${selectedIds.size} bài</button>
                    `;
                }
            } else {
                buttonsHTML = `<span style="font-size: 0.85rem; color: var(--text-muted); font-style: italic; padding: 4px;">Tích chọn tin bài để thực hiện hành động hàng loạt</span>`;
            }
            batchButtons.innerHTML = buttonsHTML;
        }

        // Cập nhật tóm tắt sự kiện trực tiếp từ bảng Excel (blur save)
        async function updateExcelSummary(id, element) {
            const newSummary = element.innerText.trim();
            try {
                const res = await fetch(`/api/articles/${id}/update-summary`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ summary: newSummary })
                });
                const result = await res.json();
                if (result.success) {
                    showToast("✍️ Đã cập nhật tóm tắt vụ việc!");
                    // Cập nhật mảng local articlesData để dữ liệu đồng bộ
                    const art = articlesData.find(a => a.id === id);
                    if (art) art.summary = newSummary;
                } else {
                    showToast("Không thể cập nhật tóm tắt", "danger");
                }
            } catch (err) {
                showToast("Lỗi kết nối khi cập nhật tóm tắt", "danger");
            }
        }

        // Process batch evaluation
        async function batchEvaluate(statusVal) {
            if (selectedIds.size === 0) return;
            const ids = Array.from(selectedIds);
            
            const confirmMsg = statusVal === 1 
                ? `Bạn có chắc muốn PHÊ DUYỆT ${ids.length} bài viết đã chọn không?`
                : `Bạn có chắc muốn LOẠI BỎ ${ids.length} bài viết đã chọn không?`;
                
            if (!confirm(confirmMsg)) return;
            
            showToast(`Đang xử lý ${ids.length} bài viết...`, 'warning');
            
            try {
                const res = await fetch('/api/articles/batch-evaluate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        ids: ids,
                        human_evaluation: statusVal
                    })
                });
                const result = await res.json();
                if (result.success) {
                    showToast(`Đã xử lý thành công hàng loạt ${ids.length} bài viết!`);
                    selectedIds.clear();
                    fetchStats();
                    fetchArticles();
                } else {
                    showToast("Xử lý hàng loạt thất bại", "danger");
                }
            } catch (err) {
                showToast("Lỗi kết nối máy chủ", "danger");
            }
        }

        // Send multiple selected articles to Telegram
        async function batchSendTelegram() {
            if (selectedIds.size === 0) return;
            const ids = Array.from(selectedIds);
            
            if (!confirm(`Bạn có chắc muốn PHÁT SÓNG ${ids.length} bài viết đã chọn lên Telegram không?`)) return;
            
            showToast(`Đang gửi ${ids.length} bài viết lên Telegram...`, 'warning');
            
            try {
                const res = await fetch('/api/articles/batch-telegram', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ids: ids })
                });
                const result = await res.json();
                if (result.success) {
                    showToast(`✈️ Đã phát sóng thành công ${result.count} bài lên Telegram!`);
                    selectedIds.clear();
                    fetchStats();
                    fetchArticles();
                } else {
                    showToast(`Gửi hàng loạt lỗi: ${result.error}`, "danger");
                }
            } catch (err) {
                showToast("Lỗi kết nối gửi Telegram", "danger");
            }
        }

        // Xử lý Phê Duyệt / Từ Chối
        async function evaluateArticle(id, statusVal) {
            let summaryText = "";
            const summaryEl = document.getElementById(`summary-${id}`);
            if (summaryEl) {
                summaryText = summaryEl.value.trim();
            } else {
                // Đang trong view Excel
                const localArt = articlesData.find(a => a.id === id);
                summaryText = localArt ? (localArt.summary || "") : "";
            }
            
            try {
                const res = await fetch(`/api/articles/${id}/evaluate`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        human_evaluation: statusVal,
                        summary: summaryText
                    })
                });
                const result = await res.json();
                if (result.success) {
                    showToast(statusVal === 1 ? "Đã duyệt chấp nhận tin bài thành công!" : "Đã loại bỏ tin bài khỏi danh sách!");
                    fetchStats();
                    fetchArticles();
                } else {
                    showToast("Thao tác thất bại", "danger");
                }
            } catch (err) {
                showToast("Lỗi kết nối khi duyệt bài", "danger");
            }
        }

        // Xử lý Gửi Telegram
        async function sendToTelegram(id) {
            showToast("Đang gửi báo cáo lên Telegram...", "warning");
            
            try {
                const res = await fetch(`/api/articles/${id}/telegram`, {
                    method: 'POST'
                });
                const result = await res.json();
                if (result.success) {
                    showToast("✈️ Phát tin thành công lên kênh Telegram!");
                    fetchStats();
                    fetchArticles();
                } else {
                    showToast(`Lỗi gửi tin: ${result.error}`, "danger");
                }
            } catch (err) {
                showToast("Lỗi kết nối máy chủ Telegram", "danger");
            }
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/config', methods=['GET', 'POST'])
def config_api():
    if request.method == 'GET':
        return jsonify({
            "TELEGRAM_BOT": get_setting("TELEGRAM_BOT"),
            "TELEGRAM_CHAT_ID": get_setting("TELEGRAM_CHAT_ID")
        })
    else:
        data = request.json or {}
        save_setting("TELEGRAM_BOT", data.get("TELEGRAM_BOT", "").strip())
        save_setting("TELEGRAM_CHAT_ID", data.get("TELEGRAM_CHAT_ID", "").strip())
        return jsonify({"success": True})

@app.route('/api/stats')
def stats_api():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # 1. Đếm bài chờ hậu kiểm (domain_id > 0 và human_evaluation IS NULL)
    cursor.execute("SELECT COUNT(*) FROM classified_articles WHERE domain_id > 0 AND human_evaluation IS NULL")
    pending = cursor.fetchone()[0]
    
    # 2. Đếm bài được chọn (human_evaluation = 1 và chưa gửi telegram)
    cursor.execute("SELECT COUNT(*) FROM classified_articles WHERE human_evaluation = 1 AND (telegram_sent = 0 OR telegram_sent IS NULL)")
    approved = cursor.fetchone()[0]
    
    # 3. Đếm bài đã gửi Telegram (human_evaluation = 1 và đã gửi telegram)
    cursor.execute("SELECT COUNT(*) FROM classified_articles WHERE human_evaluation = 1 AND telegram_sent = 1")
    telegram_sent = cursor.fetchone()[0]
    
    # 4. Đếm bài bị loại (human_evaluation = 0)
    cursor.execute("SELECT COUNT(*) FROM classified_articles WHERE human_evaluation = 0")
    rejected = cursor.fetchone()[0]
    
    # 5. Tổng số bài AI đã phân loại khớp (domain_id > 0)
    cursor.execute("SELECT COUNT(*) FROM classified_articles WHERE domain_id > 0")
    total = cursor.fetchone()[0]
    
    conn.close()
    return jsonify({
        "pending": pending,
        "approved": approved,
        "telegram_sent": telegram_sent,
        "rejected": rejected,
        "total": total
    })

@app.route('/api/articles')
def articles_api():
    status = request.args.get('status', 'pending')
    sort = request.args.get('sort', 'date_desc')

    # Map tham số sort sang mệnh đề ORDER BY an toàn (whitelist)
    sort_map = {
        'date_desc':  'ca.classified_at DESC',
        'date_asc':   'ca.classified_at ASC',
        'score_desc': 'ca.confidence_score DESC, ca.classified_at DESC',
        'pub_desc':   'ra.published_date DESC, ca.classified_at DESC',
    }
    order_by = sort_map.get(sort, 'ca.classified_at DESC')

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    if status == 'pending':
        # Tin bài khớp nhưng chưa được duyệt
        cursor.execute(f'''
            SELECT ca.*, ra.source_name, ra.source_type, ra.published_date AS raw_published_date
            FROM classified_articles ca
            LEFT JOIN raw_articles ra ON ca.raw_article_id = ra.id
            WHERE ca.domain_id > 0 AND ca.human_evaluation IS NULL
            ORDER BY {order_by}
        ''')
    elif status == 'approved':
        # Tin bài được duyệt nhưng chưa gửi telegram
        cursor.execute(f'''
            SELECT ca.*, ra.source_name, ra.source_type, ra.published_date AS raw_published_date
            FROM classified_articles ca
            LEFT JOIN raw_articles ra ON ca.raw_article_id = ra.id
            WHERE ca.human_evaluation = 1 AND (ca.telegram_sent = 0 OR ca.telegram_sent IS NULL)
            ORDER BY {order_by}
        ''')
    elif status == 'telegram':
        # Tin bài đã gửi telegram
        cursor.execute(f'''
            SELECT ca.*, ra.source_name, ra.source_type, ra.published_date AS raw_published_date
            FROM classified_articles ca
            LEFT JOIN raw_articles ra ON ca.raw_article_id = ra.id
            WHERE ca.human_evaluation = 1 AND ca.telegram_sent = 1
            ORDER BY {order_by}
        ''')
    else:
        # Tin bài bị reject
        cursor.execute(f'''
            SELECT ca.*, ra.source_name, ra.source_type, ra.published_date AS raw_published_date
            FROM classified_articles ca
            LEFT JOIN raw_articles ra ON ca.raw_article_id = ra.id
            WHERE ca.human_evaluation = 0
            ORDER BY {order_by}
        ''')
        
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    # Gán tên Lĩnh vực bảo vệ tiếng Việt cho dễ hiểu
    for row in rows:
        dom_id = row.get("domain_id", 0)
        row["domain_name"] = DOMAINS.get(dom_id, "Không xác định")
        
    return jsonify(rows)

@app.route('/api/articles/<int:id>/evaluate', methods=['POST'])
def evaluate_api(id):
    data = request.json or {}
    human_evaluation = data.get("human_evaluation") # 1 hoặc 0
    summary = data.get("summary", "")
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    if human_evaluation == 0:
        # Khi loại bỏ, reset trạng thái đã gửi telegram về 0
        cursor.execute('''
            UPDATE classified_articles 
            SET human_evaluation = ?, summary = ?, telegram_sent = 0
            WHERE id = ?
        ''', (human_evaluation, summary, id))
    else:
        # Cập nhật đánh giá và nội dung tóm tắt sau hậu kiểm
        cursor.execute('''
            UPDATE classified_articles 
            SET human_evaluation = ?, summary = ?
            WHERE id = ?
        ''', (human_evaluation, summary, id))
    
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/articles/<int:id>/update-summary', methods=['POST'])
def update_summary_api(id):
    data = request.json or {}
    summary = data.get("summary", "")
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE classified_articles 
        SET summary = ?
        WHERE id = ?
    ''', (summary, id))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/articles/<int:id>/telegram', methods=['POST'])
def telegram_api(id):
    # Lấy thông tin bài viết
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT ca.*, ra.source_name, ra.published_date 
        FROM classified_articles ca
        LEFT JOIN raw_articles ra ON ca.raw_article_id = ra.id
        WHERE ca.id = ?
    ''', (id,))
    article = cursor.fetchone()
    conn.close()
    
    if not article:
        return jsonify({"success": False, "error": "Không tìm thấy bài viết"}), 404
        
    # Chuẩn bị thông tin cấu hình Telegram
    bot_token = get_setting("TELEGRAM_BOT")
    chat_id = get_setting("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        return jsonify({"success": False, "error": "Vui lòng nhập đầy đủ BOT TOKEN và CHAT ID ở cột cấu hình bên phải trước!"}), 400
        
    domain_name = DOMAINS.get(article["domain_id"], "Không xác định")
    
    import html
    import re
    
    def clean_and_escape(text):
        if not text:
            return ""
        # Loại bỏ các thẻ HTML để tránh lỗi định dạng
        clean_text = re.sub(r'<[^>]+>', '', text)
        return html.escape(clean_text)
        
    safe_title = clean_and_escape(article["title"])
    safe_url = html.escape(article["url"] or "")
    safe_source = clean_and_escape(article["source_name"])
    safe_domain = clean_and_escape(domain_name)
    safe_reason = clean_and_escape(article["match_reason"])
    safe_summary = clean_and_escape(article["summary"])
    
    pub_date = article.get("published_date") or "Không xác định"
    safe_pub_date = clean_and_escape(str(pub_date))
    
    # Tạo format tin gửi Telegram bằng HTML để an toàn tuyệt đối
    message = (
        "🏛️ <b>BÁO CÁO PHÁT HIỆN HẬU KIỂM - VKS BOT</b> 🏛️\n"
        "──────────────────────────\n"
        f"📌 <b>Tiêu đề</b>: {safe_title}\n"
        f"📅 <b>Ngày đăng</b>: {safe_pub_date}\n"
        f"🔗 <b>Link bài viết</b>: {safe_url}\n"
        f"📰 <b>Nguồn</b>: {safe_source}\n"
        f"⚖️ <b>Lĩnh vực bảo vệ</b>: {safe_domain}\n"
        f"🔍 <b>Lý do AI phát hiện</b>: {safe_reason}\n"
        "──────────────────────────\n"
        f"✍️ <b>Tóm tắt sự kiện</b> (Đã kiểm duyệt):\n"
        f"<i>{safe_summary}</i>"
    )
    
    # Gửi qua API Telegram
    telegram_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    
    try:
        response = requests.post(telegram_url, json=payload, timeout=15)
        res_data = response.json()
        if response.status_code == 200 and res_data.get("ok"):
            # Cập nhật trạng thái telegram_sent = 1 trong CSDL
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("UPDATE classified_articles SET telegram_sent = 1 WHERE id = ?", (id,))
            conn.commit()
            conn.close()
            return jsonify({"success": True})
        else:
            error_msg = res_data.get("description", "Không rõ nguyên nhân")
            return jsonify({"success": False, "error": f"Lỗi API Telegram: {error_msg}"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": f"Lỗi kết nối: {str(e)}"}), 500

@app.route('/api/articles/batch-evaluate', methods=['POST'])
def batch_evaluate_api():
    data = request.json or {}
    ids = data.get("ids", [])
    human_evaluation = data.get("human_evaluation") # 1 hoặc 0
    
    if not ids:
        return jsonify({"success": False, "error": "Chưa chọn bài viết"}), 400
        
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Cập nhật trạng thái duyệt cho tất cả các id đã chọn
    placeholders = ",".join("?" for _ in ids)
    if human_evaluation == 0:
        # Nếu loại bỏ hàng loạt, reset trạng thái telegram_sent về 0
        cursor.execute(f'''
            UPDATE classified_articles 
            SET human_evaluation = ?, telegram_sent = 0
            WHERE id IN ({placeholders})
        ''', [human_evaluation] + ids)
    else:
        cursor.execute(f'''
            UPDATE classified_articles 
            SET human_evaluation = ?
            WHERE id IN ({placeholders})
        ''', [human_evaluation] + ids)
    
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/articles/batch-telegram', methods=['POST'])
def batch_telegram_api():
    data = request.json or {}
    ids = data.get("ids", [])
    
    if not ids:
        return jsonify({"success": False, "error": "Chưa chọn bài viết"}), 400
        
    bot_token = get_setting("TELEGRAM_BOT")
    chat_id = get_setting("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        return jsonify({"success": False, "error": "Vui lòng nhập đầy đủ BOT TOKEN và CHAT ID ở cột cấu hình bên phải trước!"}), 400
        
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    placeholders = ",".join("?" for _ in ids)
    cursor.execute(f'''
        SELECT ca.*, ra.source_name, ra.published_date 
        FROM classified_articles ca
        LEFT JOIN raw_articles ra ON ca.raw_article_id = ra.id
        WHERE ca.id IN ({placeholders})
    ''', ids)
    articles = cursor.fetchall()
    conn.close()
    
    success_count = 0
    errors = []
    
    for article in articles:
        domain_name = DOMAINS.get(article["domain_id"], "Không xác định")
        
        import html
        import re
        
        def clean_and_escape(text):
            if not text:
                return ""
            clean_text = re.sub(r'<[^>]+>', '', text)
            return html.escape(clean_text)
            
        safe_title = clean_and_escape(article["title"])
        safe_url = html.escape(article["url"] or "")
        safe_source = clean_and_escape(article["source_name"])
        safe_domain = clean_and_escape(domain_name)
        safe_reason = clean_and_escape(article["match_reason"])
        safe_summary = clean_and_escape(article["summary"])
        
        pub_date = article.get("published_date") or "Không xác định"
        safe_pub_date = clean_and_escape(str(pub_date))
        
        message = (
            "🏛️ <b>BÁO CÁO PHÁT HIỆN HẬU KIỂM - VKS BOT</b> 🏛️\n"
            "──────────────────────────\n"
            f"📌 <b>Tiêu đề</b>: {safe_title}\n"
            f"📅 <b>Ngày đăng</b>: {safe_pub_date}\n"
            f"🔗 <b>Link bài viết</b>: {safe_url}\n"
            f"📰 <b>Nguồn</b>: {safe_source}\n"
            f"⚖️ <b>Lĩnh vực bảo vệ</b>: {safe_domain}\n"
            f"🔍 <b>Lý do AI phát hiện</b>: {safe_reason}\n"
            "──────────────────────────\n"
            f"✍️ <b>Tóm tắt sự kiện</b> (Đã kiểm duyệt):\n"
            f"<i>{safe_summary}</i>"
        )
        
        telegram_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }
        
        try:
            response = requests.post(telegram_url, json=payload, timeout=10)
            res_data = response.json()
            if response.status_code == 200 and res_data.get("ok"):
                success_count += 1
                # Cập nhật trạng thái telegram_sent = 1
                conn_write = sqlite3.connect(DB_FILE)
                cursor_write = conn_write.cursor()
                cursor_write.execute("UPDATE classified_articles SET telegram_sent = 1 WHERE id = ?", (article["id"],))
                conn_write.commit()
                conn_write.close()
            else:
                error_msg = res_data.get("description", "Không rõ nguyên nhân")
                errors.append(f"ID {article['id']}: {error_msg}")
        except Exception as e:
            errors.append(f"ID {article['id']}: {str(e)}")
            
    if success_count > 0:
        return jsonify({"success": True, "count": success_count, "errors": errors})
    else:
        return jsonify({"success": False, "error": f"Lỗi gửi tin: {', '.join(errors[:3])}"}), 500

def get_local_ip():
    """Tự động dò tìm IP mạng nội bộ (LAN) đang hoạt động trên máy tính của bạn"""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

if __name__ == '__main__':
    local_ip = get_local_ip()
    print("\n🚀 ĐANG KHỞI CHẠY GIAO DIỆN HẬU KIỂM VKS BOT DASHBOARD...")
    print(f"👉 Để truy cập trên máy này: http://127.0.0.1:5000")
    if local_ip != "127.0.0.1":
        print(f"👉 Để thiết bị khác cùng mạng Wi-Fi truy cập: http://{local_ip}:5000\n")
    app.run(host='0.0.0.0', port=5000, debug=True)
