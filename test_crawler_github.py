# -*- coding: utf-8 -*-
"""
test_crawler_github.py
=============================================================================
Bản nâng cấp tối ưu hóa đặc trị cho môi trường GITHUB ACTIONS CI/CD.
Kế thừa toàn bộ logic cốt lõi ổn định từ test_crawler_basic.py và tích hợp thêm:
- Cơ chế Định tuyến Proxy Việt Nam Chủ động (Selective Proxy Routing)
- Tối ưu hóa tải HTML qua Proxy cho Newspaper4k NLP Summarization
=============================================================================
"""

import os
import sys
import io
import time
import random
import datetime
import urllib.parse
import urllib3
import requests
import feedparser
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

# Tải biến môi trường từ file .env nếu có
load_dotenv()

# Đảm bảo xuất dữ liệu dạng UTF-8 trên mọi nền tảng (đặc biệt là môi trường CI/CD không có TTY)
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Khóa luồng để tránh đè chữ khi in ra console song song
print_lock = threading.Lock()

def safe_print(*args, **kwargs):
    with print_lock:
        sys.stdout.write(" ".join(map(str, args)) + kwargs.get("end", "\n"))
        sys.stdout.flush()

# Ghi đè hàm print mặc định để đồng bộ luồng
print = safe_print

# Import các hàm nghiệp vụ ổn định từ crawler_db_github
try:
    from crawler_db_github import init_db, save_articles, get_active_rss_sources, update_source_status, filter_new_urls
except ImportError:
    # Hỗ trợ tìm đường dẫn tương đối khi chạy trên runner
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from crawler_db_github import init_db, save_articles, get_active_rss_sources, update_source_status, filter_new_urls

# Khởi tạo adapter SSL cho phép kết nối tới các trang web có cấu hình TLS/SSL cũ (Legacy Renegotiation)
class LegacySSLAdapter(requests.adapters.HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = urllib3.util.ssl_.create_urllib3_context()
        ctx.check_hostname = False  # Vô hiệu hóa check_hostname tránh lỗi ValueError
        ctx.options |= 0x40000  # SSL_OP_ALLOW_UNSAFE_LEGACY_RENEGOTIATION
        kwargs['ssl_context'] = ctx
        return super(LegacySSLAdapter, self).init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        ctx = urllib3.util.ssl_.create_urllib3_context()
        ctx.check_hostname = False
        ctx.options |= 0x40000
        kwargs['ssl_context'] = ctx
        return super(LegacySSLAdapter, self).proxy_manager_for(*args, **kwargs)

def clean_xml_content(content):
    import re
    # Sửa lỗi ký tự '&' chưa được escape trong XML (ngoại trừ các thực thể chuẩn)
    content = re.sub(r'&(?!(amp|lt|gt|quot|apos);)', '&amp;', content)
    # Loại bỏ các ký tự điều khiển ASCII không hợp lệ trong XML (ngoại trừ \t, \n, \r)
    content = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', content)
    return content

def get_vietnam_proxy():
    """Lấy cấu hình Proxy Việt Nam từ biến môi trường"""
    return os.getenv("VIETNAM_PROXY") or os.getenv("GITHUB_PROXY") or os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")

# --- HÀM CRAWL RSS ĐỘNG TÍCH HỢP PROXY CHỦ ĐỘNG ---
def crawl_rss(source_id, source_name, feed_url, limit=10):
    """Lấy toàn bộ dữ liệu từ một nguồn RSS cụ thể (Có Proxy Routing cho GitHub Actions)"""
    # Tránh bị Cloudflare / Web Server chặn do bắn quá nhiều request đồng thời
    time.sleep(random.uniform(0.1, 3.5))
    
    print(f"🔄 Đang quét: {source_name}...")
    articles = []
    failed_report = {}
    
    # Tự động điều chỉnh headers dựa trên tên miền
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
        # Thiết lập requests Session mounted với LegacySSLAdapter
        session = requests.Session()
        session.mount("https://", LegacySSLAdapter())
        session.mount("http://", LegacySSLAdapter())
        
        # CƠ CHẾ 4: ĐỊNH TUYẾN PROXY VIỆT NAM CHỦ ĐỘNG
        vietnam_proxy = get_vietnam_proxy()
        proxies = None
        if vietnam_proxy and any(dm in parsed_domain for dm in ["hanoimoi.vn", "kinhtemoitruong.vn", "hanoimoi.com.vn", "qdnd.vn"]):
            proxies = {
                "http": vietnam_proxy,
                "https": vietnam_proxy
            }
            print(f"🌐 [Proxy] Đang định tuyến cào nguồn {source_name} qua Proxy Việt Nam...")
            
        r = None
        conn_err = None
        try:
            r = session.get(feed_url, headers=headers, proxies=proxies, timeout=10)
            
            # Nếu bị chặn bởi Cloudflare rate-limit, thử lại thông minh
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
                raise requests.RequestException(f"HTTP {r.status_code}")
        except Exception as e:
            conn_err = e
            
        # CƠ CHẾ DỰ PHÒNG: GOOGLE WEB CACHE BYPASS TỰ ĐỘNG CHO RSS
        if r is None or r.status_code != 200:
            print(f"⚠️ [Bypass Web Cache] Nguồn {source_name} lỗi kết nối ({conn_err}). Đang chuyển hướng cào qua Google Cache...")
            try:
                cache_url = f"https://webcache.googleusercontent.com/search?q=cache:{feed_url}"
                cache_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "vi-VN,vi;q=0.9",
                    "Referer": "https://www.google.com/"
                }
                r = session.get(cache_url, headers=cache_headers, timeout=12)
                if r.status_code == 200:
                    print(f"🔮 [Google Cache] Phục hồi kết nối thành công cho {source_name}!")
            except Exception as cache_err:
                conn_err = f"{conn_err} & Cache Lỗi: {cache_err}"

        if r is None or r.status_code != 200:
            error_msg = f"Lỗi kết nối hoàn toàn: {conn_err}"
            print(f"❌ {source_name} thất bại: {error_msg}")
            update_source_status(source_id, last_error=error_msg, is_active=1)
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
            update_source_status(source_id, last_error=error_msg, is_active=1)
            failed_report[source_name] = (feed_url, error_msg)
            return [], failed_report
            
        entries = feed.entries[:limit]
        for entry in entries:
            pub_date = entry.get('published') or entry.get('updated') or str(datetime.datetime.now())
            summary = entry.get('summary') or entry.get('description') or ""
            title = entry.get('title', 'Không có tiêu đề')
            url = entry.get('link', '')
            
            article = {
                'source_type': 'news',
                'source_name': source_name,
                'title': title,
                'url': url,
                'summary': summary,
                'published_date': pub_date
            }
            articles.append(article)
                
        # Cập nhật trạng thái thành công
        update_source_status(source_id, last_error=None, is_active=1)
        print(f"✅ {source_name}: Lấy thành công {len(articles)} bài viết.")
        return articles, {}
        
    except Exception as e:
        error_msg = f"Lỗi hệ thống: {type(e).__name__} - {str(e)}"
        print(f"❌ {source_name} thất bại: {error_msg}")
        update_source_status(source_id, last_error=error_msg, is_active=1)
        failed_report[source_name] = (feed_url, error_msg)
        return [], failed_report

# --- TỐI ƯU CÀO BÀI CHI TIẾT QUA PROXY CHO NEWSPAPER4K ---
def fetch_single_article_summary(article):
    """Tải và trích xuất tóm tắt chuyên sâu bằng newspaper4k, tích hợp Proxy và Legacy SSL"""
    url = article.get('url')
    if not url:
        return
    try:
        from newspaper import Article, Config
        config = Config()
        config.language = 'vi'
        config.request_timeout = 8
        config.max_summary_sent = 7
        
        parsed_domain = urllib.parse.urlparse(url).netloc.lower()
        if any(dm in parsed_domain for dm in ["hanoimoi.vn", "kinhtemoitruong.vn", "hanoimoi.com.vn", "qdnd.vn"]):
            user_agent = "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_patched.html)"
        else:
            user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
        config.user_agent = user_agent
        
        # Tải HTML chủ động thông qua requests Session có tích hợp Proxy Việt Nam
        session = requests.Session()
        session.mount("https://", LegacySSLAdapter())
        session.mount("http://", LegacySSLAdapter())
        
        vietnam_proxy = get_vietnam_proxy()
        proxies = None
        if vietnam_proxy and any(dm in parsed_domain for dm in ["hanoimoi.vn", "kinhtemoitruong.vn", "hanoimoi.com.vn", "qdnd.vn"]):
            proxies = {
                "http": vietnam_proxy,
                "https": vietnam_proxy
            }
            
        headers = {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9"
        }
        
        # Tải trang
        r = None
        conn_err = None
        try:
            r = session.get(url, headers=headers, proxies=proxies, timeout=12)
            if r.status_code != 200:
                raise requests.RequestException(f"HTTP {r.status_code}")
        except Exception as e:
            conn_err = e
            
        # CƠ CHẾ DỰ PHÒNG: GOOGLE WEB CACHE CHO ARTICLE
        if r is None or r.status_code != 200:
            try:
                cache_url = f"https://webcache.googleusercontent.com/search?q=cache:{url}"
                cache_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "vi-VN,vi;q=0.9",
                    "Referer": "https://www.google.com/"
                }
                r = session.get(cache_url, headers=cache_headers, timeout=12)
            except Exception:
                r = None

        if r and r.status_code == 200:
            art = Article(url, config=config)
            # Truyền trực tiếp HTML đã cào thành công qua proxy hoặc Google Cache vào newspaper
            art.set_html(r.text)
            art.parse()
            art.nlp()
            summary = art.summary.strip()
            if summary:
                article['summary'] = " ".join(summary.split())
                print(f"🟢 Đã tóm tắt bằng 4k: {article['title'][:45]}...")
            elif art.text:
                snippet = " ".join(art.text.split()[:50]) + "..."
                article['summary'] = snippet
                print(f"🟢 Đã tóm tắt bằng 4k (lấy đoạn ngắn): {article['title'][:45]}...")
    except Exception:
        pass

# --- HÀM MAIN CHẠY TỔNG HỢP ---
def main():
    print("================================================================================")
    print("🚀 BẮT ĐẦU CHẠY CRAWLER GITHUB ACTIONS - RSS PHÁP LUẬT & NỘI CHÍNH 🚀")
    if os.getenv("GITHUB_ACTIONS") == "true":
        print("🖥️ Môi trường: GITHUB ACTIONS CI/CD RUNNER")
    else:
        print("🖥️ Môi trường: CÁ NHÂN / LOCAL")
        
    vietnam_proxy = get_vietnam_proxy()
    if vietnam_proxy:
        print(f"🌐 Proxy Việt Nam được kích hoạt thành công: {vietnam_proxy}")
    else:
        print("⚠️ Cảnh báo: Không phát hiện VIETNAM_PROXY. Sẽ cào trực tiếp không dùng proxy.")
    print("================================================================================\n")
    
    # Tải trước nltk data trên luồng chính để tránh xung đột luồng
    import nltk
    for pkg in ['punkt', 'punkt_tab']:
        try:
            nltk.data.find(f'tokenizers/{pkg}')
        except LookupError:
            print(f"📥 Đang tải gói dữ liệu NLTK '{pkg}' trên luồng chính...")
            nltk.download(pkg, quiet=True)
            
    # 1. Khởi tạo DB nếu chưa có
    init_db()
    
    # 2. Đọc danh sách nguồn RSS đang hoạt động từ DB
    active_sources = get_active_rss_sources()
    print(f"\n📂 Đã tải {len(active_sources)} nguồn RSS đang hoạt động từ cơ sở dữ liệu.")
    
    all_data = []
    all_failed_sources = {}
    
    # 3. Quét SONG SONG các nguồn RSS sử dụng ThreadPoolExecutor để tăng hiệu năng tối đa
    # Giới hạn luồng xuống 20 để tránh quá tải trên GitHub Runner cấu hình trung bình
    max_workers = 20
    print(f"⚡ Đang tiến hành quét song song {len(active_sources)} nguồn bằng {max_workers} luồng đồng thời...")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                crawl_rss,
                source_id=src['id'],
                source_name=src['source_name'],
                feed_url=src['rss_url'],
                limit=10  # Lấy tối đa 10 bài mới nhất mỗi chuyên mục
            ): src for src in active_sources
        }
        
        for future in as_completed(futures):
            src = futures[future]
            try:
                articles, failed = future.result()
                all_data.extend(articles)
                all_failed_sources.update(failed)
            except Exception as e:
                error_msg = f"Lỗi luồng chạy: {type(e).__name__} - {str(e)}"
                print(f"❌ {src['source_name']} thất bại do lỗi luồng: {error_msg}")
                all_failed_sources[src['source_name']] = (src['rss_url'], error_msg)
        
    # 4. Lọc ra CHỈ bài viết MỚI chưa có trong DB, rồi bổ sung tóm tắt và lưu
    if all_data:
        # Lọc ra các bài viết chưa có trong DB dựa trên URL
        urls = [art['url'] for art in all_data if art.get('url')]
        new_urls = filter_new_urls(urls)
        new_articles = [art for art in all_data if art.get('url') in new_urls]
        
        if new_articles:
            print(f"\n📝 Phát hiện {len(new_articles)} bài viết mới chưa có trong DB.")
            
            # Chỉ dùng Newspaper4k cho các bài CHƯA CÓ summary từ RSS (hoặc summary quá ngắn)
            articles_need_summary = [art for art in new_articles 
                                     if not art.get('summary') or len(art.get('summary', '')) < 30]
            
            if articles_need_summary:
                print(f"⚡ Đang trích xuất tóm tắt chuyên sâu cho {len(articles_need_summary)} bài bằng 10 luồng (Newspaper4k)...")
                start_time = time.time()
                
                with ThreadPoolExecutor(max_workers=10) as summary_executor:
                    summary_futures = [summary_executor.submit(fetch_single_article_summary, art) for art in articles_need_summary]
                    for future in as_completed(summary_futures):
                        try:
                            future.result()
                        except Exception:
                            pass
                            
                elapsed = time.time() - start_time
                print(f"✅ Đã hoàn thành tóm tắt {len(articles_need_summary)} bài trong {elapsed:.2f} giây.")
            else:
                print("✨ Tất cả bài viết mới đã có tóm tắt từ RSS, không cần dùng Newspaper4k.")
            
            # CHỈ lưu bài viết MỚI vào CSDL
            print(f"\n💾 Đang lưu {len(new_articles)} bài viết mới vào CSDL...")
            save_start = time.time()
            saved_count = save_articles(new_articles)
            save_elapsed = time.time() - save_start
            print(f"🎉 HOÀN THÀNH: Đã lưu {saved_count} bài mới vào DB trong {save_elapsed:.2f} giây (tổng cào: {len(all_data)} bài, đã lọc {len(all_data) - len(new_articles)} bài trùng).")
        else:
            print("\n✨ Không có bài viết mới nào — tất cả đã có trong DB.")
    else:
        print("\n⚠️ Không có bài viết nào được tìm thấy.")
        
    # 5. BÁO CÁO CÁC NGUỒN BỊ LỖI (NẾU CÓ)
    print("\n================ BÁO CÁO NGUỒN RSS BỊ LỖI ================")
    if all_failed_sources:
        print(f"🚨 Phát hiện {len(all_failed_sources)} nguồn gặp sự cố kết nối hoặc định dạng:")
        for idx, (name, (url, err)) in enumerate(sorted(all_failed_sources.items()), 1):
            print(f"{idx}. 🔴 {name}")
            print(f"   - Đường dẫn: {url}")
            print(f"   - Chi tiết lỗi: {err}")
    else:
        print("✅ Tuyệt vời! Toàn bộ các nguồn RSS hoạt động trơn tru không lỗi.")
    print("==========================================================")

if __name__ == "__main__":
    main()
