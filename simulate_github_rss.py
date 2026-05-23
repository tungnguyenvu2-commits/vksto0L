"""
simulate_github_rss.py
==================================================================================
Script giả lập môi trường và cấu hình kết nối của GITHUB ACTIONS / CLOUD RUNNERS.
Phiên bản mới: Sử dụng y nguyên hàm crawl_rss từ test_crawler_basic.py để chạy thực tế
và chẩn đoán kết quả vượt lỗi 403 bằng Proxy Việt Nam.

LƯU Ý: File test_crawler_basic.py hoàn toàn giữ nguyên bản gốc không sửa đổi.
==================================================================================
"""

import os
import sys
import time
import datetime
import urllib.parse
import urllib3
import requests
import feedparser
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

# Tải biến môi trường
load_dotenv()

# Đảm bảo in tiếng Việt chuẩn trên Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Khóa luồng để tránh đè chữ khi in ra console song song
print_lock = threading.Lock()

def safe_print(*args, **kwargs):
    with print_lock:
        sys.stdout.write(" ".join(map(str, args)) + kwargs.get("end", "\n"))
        sys.stdout.flush()

# Ghi đè hàm print mặc định
print = safe_print

# Khởi tạo adapter SSL xử lý các trang báo có cấu hình TLS cũ (Legacy Renegotiation)
class LegacySSLAdapter(requests.adapters.HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = urllib3.util.ssl_.create_urllib3_context()
        ctx.check_hostname = False
        ctx.options |= 0x40000  # SSL_OP_ALLOW_UNSAFE_LEGACY_RENEGOTIATION
        kwargs['ssl_context'] = ctx
        return super(LegacySSLAdapter, self).init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        ctx = urllib3.util.ssl_.create_urllib3_context()
        ctx.check_hostname = False
        ctx.options |= 0x40000
        kwargs['ssl_context'] = ctx
        return super(LegacySSLAdapter, self).proxy_manager_for(*args, **kwargs)

# Kết nối database an toàn (Hỗ trợ cả local SQLite và remote PostgreSQL)
def get_db_connection():
    db_url = os.getenv("DATABASE_URL")
    if db_url and (os.getenv("RENDER") or "postgres" in db_url):
        import psycopg2
        conn = psycopg2.connect(db_url)
        return conn, "PostgreSQL (Cloud)"
    else:
        import sqlite3
        db_file = "crawler_data.db"
        if not os.path.exists(db_file):
            db_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crawler_data.db")
        conn = sqlite3.connect(db_file)
        return conn, f"SQLite cục bộ ({db_file})"

# Tải danh sách nguồn RSS đang hoạt động
def load_rss_sources():
    try:
        conn, db_type = get_db_connection()
        print(f"🗄️ Đã kết nối thành công tới Cơ sở dữ liệu: {db_type}")
        cursor = conn.cursor()
        cursor.execute("SELECT id, source_name, rss_url, is_active FROM rss_sources WHERE is_active = 1")
        rows = cursor.fetchall()
        conn.close()
        
        sources = []
        for r in rows:
            sources.append({
                "id": r[0],
                "source_name": r[1],
                "rss_url": r[2],
                "is_active": r[3]
            })
        return sources
    except Exception as e:
        print(f"❌ Lỗi tải nguồn RSS từ Database: {e}")
        return []

def clean_xml_content(content):
    import re
    # Sửa lỗi ký tự '&' chưa được escape trong XML (ngoại trừ các thực thể chuẩn)
    content = re.sub(r'&(?!(amp|lt|gt|quot|apos);)', '&amp;', content)
    # Loại bỏ các ký tự điều khiển ASCII không hợp lệ trong XML (ngoại trừ \t, \n, \r)
    content = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', content)
    return content

# --- HÀM CRAWL RSS (COPY Y NGUYÊN TỪ TEST_CRAWLER_BASIC.PY VÀ BỔ SUNG PROXY) ---
def crawl_rss(source_id, source_name, feed_url, limit=10):
    """Lấy toàn bộ dữ liệu từ một nguồn RSS cụ thể (không lọc từ khóa, lấy tất cả)"""
    # Tránh bị Cloudflare / Web Server chặn do bắn quá nhiều request đồng thời
    import time
    import random
    time.sleep(random.uniform(0.1, 1.5)) # Rút ngắn thời gian sleep để chạy nhanh hơn trong giả lập
    
    print(f"🔄 Đang quét: {source_name}...")
    articles = []
    failed_report = {}
    
    # Tự động điều chỉnh headers dựa trên tên miền để tránh bị chặn 403 / Timeout
    import urllib.parse
    parsed_domain = urllib.parse.urlparse(feed_url).netloc.lower()
    
    if any(dm in parsed_domain for dm in ["hanoimoi.vn", "kinhtemoitruong.vn", "hanoimoi.com.vn"]):
        headers = {
            "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_patched.html)",
            "Accept": "*/*",
            "Accept-Language": "vi-VN,vi;q=0.9",
            "Connection": "keep-alive"
        }
    else:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.google.com/"
        }
    
    try:
        # Sử dụng requests Session mounted với LegacySSLAdapter để xử lý SSL lỗi thời
        session = requests.Session()
        session.mount("https://", LegacySSLAdapter())
        session.mount("http://", LegacySSLAdapter())
        
        # BỔ SUNG PROXY VIỆT NAM CHO FILE GIẢ LẬP GITHUB ACTIONS
        import os
        vietnam_proxy = os.getenv("VIETNAM_PROXY") or os.getenv("GITHUB_PROXY") or os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
        proxies = None
        if vietnam_proxy and any(dm in parsed_domain for dm in ["hanoimoi.vn", "kinhtemoitruong.vn", "hanoimoi.com.vn", "qdnd.vn"]):
            proxies = {
                "http": vietnam_proxy,
                "https": vietnam_proxy
            }
            print(f"🌐 [Proxy] Đang sử dụng Proxy Việt Nam để vượt rào cho: {source_name}")

        r = session.get(feed_url, headers=headers, proxies=proxies, timeout=10)
        
        # Nếu bị chặn bởi Cloudflare rate-limit (503/429/502/504), tiến hành thử lại sau thời gian chờ ngẫu nhiên
        if r.status_code in [429, 502, 503, 504]:
            retry_delay = random.uniform(3.0, 7.0)
            time.sleep(retry_delay)
            r = session.get(feed_url, headers=headers, proxies=proxies, timeout=10)
            
        # Vượt qua thử thách cookie của Báo Lao Động nếu gặp phải
        if "document.cookie=\"D1N=" in r.text:
            import re
            match = re.search(r'document\.cookie="([^"]+)"', r.text)
            if match:
                cookie_str = match.group(1)
                cookie_pair = cookie_str.split(';')[0].split('=')
                cookie_name = cookie_pair[0].strip()
                cookie_val = cookie_pair[1].strip()
                
                session.headers.update(headers)
                session.cookies.set(cookie_name, cookie_val, domain="laodong.vn", path="/")
                r = session.get(feed_url, proxies=proxies, timeout=10)
                
        if r.status_code != 200:
            error_msg = f"Lỗi kết nối HTTP {r.status_code}"
            print(f"❌ {source_name} thất bại: {error_msg}")
            failed_report[source_name] = (feed_url, error_msg)
            return [], failed_report
            
        # Loại bỏ BOM (\ufeff) và khoảng trắng thừa đầu/cuối XML, làm sạch XML lỗi
        xml_content = clean_xml_content(r.text.lstrip('\ufeff').strip())
        
        # Phân tích cú pháp RSS
        feed = feedparser.parse(xml_content)
        
        # Chỉ coi là lỗi nặng nếu bozo lỗi và không lấy được bài viết nào
        if feed.bozo and not feed.entries:
            error_msg = f"Lỗi XML: {feed.bozo_exception}"
            print(f"❌ {source_name} thất bại: {error_msg}")
            failed_report[source_name] = (feed_url, error_msg)
            return [], failed_report
            
        entries = feed.entries[:limit]
        for entry in entries:
            pub_date = entry.get('published') or entry.get('updated') or str(datetime.datetime.now())
            summary = entry.get('summary') or entry.get('description') or ""
            title = entry.get('title', 'Không có tiêu đề')
            url = entry.get('link', '')
            
            # Lưu đầy đủ thông tin bài viết bao gồm summary cột mới
            article = {
                'source_type': 'news',
                'source_name': source_name,
                'title': title,
                'url': url,
                'summary': summary,
                'published_date': pub_date
            }
            articles.append(article)
                
        print(f"✅ {source_name}: Lấy thành công {len(articles)} bài viết.")
        return articles, {}
        
    except Exception as e:
        error_msg = f"Lỗi hệ thống: {type(e).__name__} - {str(e)}"
        print(f"❌ {source_name} thất bại: {error_msg}")
        failed_report[source_name] = (feed_url, error_msg)
        return [], failed_report

def main():
    print("================================================================================")
    print("🚀 BẮT ĐẦU GIẢ LẬP GITHUB ACTIONS CRAWLER (TÍCH HỢP PROXY VIỆT NAM) 🚀")
    print("================================================================================")
    
    # 1. Phát hiện cấu hình Proxy Việt Nam
    vietnam_proxy = os.getenv("VIETNAM_PROXY") or os.getenv("GITHUB_PROXY") or os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
    if vietnam_proxy:
        print(f"🌐 Phát hiện cấu hình Proxy Việt Nam để vượt lỗi 403: {vietnam_proxy}")
    else:
        print("⚠️ Cảnh báo: Chưa cấu hình VIETNAM_PROXY hoặc GITHUB_PROXY trong file .env!")
        print("Script giả lập sẽ cào trực tiếp bằng dải IP hiện tại (lỗi 403 có thể xảy ra trên GitHub Actions).")
        
    # 2. Tải danh sách nguồn RSS
    sources = load_rss_sources()
    if not sources:
        print("❌ Không tìm thấy nguồn RSS nào đang hoạt động để chạy kiểm tra.")
        return
        
    # Chỉ định test nhanh 30 nguồn (ưu tiên các nguồn nhạy cảm bị 403 để chẩn đoán)
    # Lọc ra các nguồn thuộc hanoimoi, qdnd, kinhtemoitruong để đẩy lên đầu danh sách test
    targeted_sources = []
    other_sources = []
    
    for src in sources:
        url = src["rss_url"].lower()
        if any(dm in url for dm in ["hanoimoi.vn", "qdnd.vn", "kinhtemoitruong.vn"]):
            targeted_sources.append(src)
        else:
            other_sources.append(src)
            
    # Tạo danh sách test có 15 nguồn nhạy cảm và 15 nguồn thông thường khác
    sources_to_test = targeted_sources[:15] + other_sources[:15]
    
    print(f"📂 Tìm thấy {len(sources)} nguồn RSS. Bắt đầu mô phỏng {len(sources_to_test)} nguồn song song...")
    
    # 3. Quét SONG SONG các luồng mô phỏng y hệt Crawler sản xuất
    print(f"⚡ Đang tiến hành quét song song bằng 10 luồng...")
    start_audit_time = time.time()
    
    success_count = 0
    fail_count = 0
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(
                crawl_rss,
                source_id=src["id"],
                source_name=src["source_name"],
                feed_url=src["rss_url"]
            ): src for src in sources_to_test
        }
        
        for future in as_completed(futures):
            src = futures[future]
            try:
                articles, failed = future.result()
                if articles:
                    success_count += 1
                else:
                    fail_count += 1
            except Exception as e:
                print(f"❌ Lỗi luồng chạy giả lập nguồn {src['source_name']}: {e}")
                fail_count += 1
                
    elapsed = time.time() - start_audit_time
    print("\n================================================================================")
    print("🎉 HOÀN THÀNH GIẢ LẬP GITHUB ACTIONS CRAWLER!")
    print(f"⏱️ Tổng thời gian chạy: {elapsed:.2f} giây.")
    print(f"📊 Kết quả: Thành công {success_count} nguồn | Thất bại {fail_count} nguồn.")
    print("================================================================================")

if __name__ == "__main__":
    main()
