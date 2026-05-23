import os
import sqlite3
import datetime
import urllib.parse
import time
import random
import sys
import requests
from bs4 import BeautifulSoup
import re

from crawler_db import get_active_non_rss_sources, save_articles, filter_new_urls
import urllib3
import ssl

# Vô hiệu hóa cảnh báo SSL không an toàn khi dùng verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Định nghĩa adapter SSL để vượt qua lỗi unsafe legacy renegotiation
class LegacySSLAdapter(requests.adapters.HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = urllib3.util.ssl_.create_urllib3_context()
        ctx.check_hostname = False  # Vô hiệu hóa check_hostname để tránh lỗi với verify=False
        ctx.options |= 0x40000  # SSL_OP_ALLOW_UNSAFE_LEGACY_RENEGOTIATION
        try:
            ctx.set_ciphers('DEFAULT@SECLEVEL=1')
        except Exception:
            pass
        kwargs['ssl_context'] = ctx
        return super(LegacySSLAdapter, self).init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        ctx = urllib3.util.ssl_.create_urllib3_context()
        ctx.check_hostname = False  # Vô hiệu hóa check_hostname để tránh lỗi với verify=False
        ctx.options |= 0x40000
        try:
            ctx.set_ciphers('DEFAULT@SECLEVEL=1')
        except Exception:
            pass
        kwargs['ssl_context'] = ctx
        return super(LegacySSLAdapter, self).proxy_manager_for(*args, **kwargs)

def get_headers(url):
    import urllib.parse
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower()
    if "hanoimoi.vn" in domain or "kinhtemoitruong.vn" in domain or "hanoimoi.com.vn" in domain:
        return {
            "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9",
            "Connection": "keep-alive"
        }
    return {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.google.com/"
    }

HEADERS = get_headers("")


def safe_print(message):
    """
    Hàm in an toàn (safe print) tự động tránh crash khi gặp ký tự unicode
    trên các terminal Windows cũ không hỗ trợ đầy đủ tiếng Việt UTF-8.
    """
    try:
        print(message)
    except UnicodeEncodeError:
        try:
            encoding = sys.stdout.encoding or 'ascii'
            print(message.encode(encoding, errors='replace').decode(encoding))
        except Exception:
            try:
                print(message.encode('ascii', errors='ignore').decode('ascii'))
            except Exception:
                pass

def clean_text(text):
    if not text:
        return ""
    return " ".join(text.strip().split())

def smart_fallback_extractor(html_content, base_url):
    """
    Bộ bóc tách dự phòng siêu thông minh (Smart Fallback Extractor).
    Tự động phân tích cấu trúc DOM và lọc ra các liên kết tin tức/văn bản kèm tiêu đề 
    khi giao diện trang web bị thay đổi hoặc không khớp với các bộ chọn (selectors) cũ.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    articles = []
    
    # Bỏ qua các khối điều hướng, footer thông dụng để tránh lấy nhầm tin rác
    for noise in soup.select("nav, footer, script, style, .menu, .nav, .footer"):
        noise.decompose()
        
    seen_urls = set()
    
    # Duyệt qua toàn bộ thẻ liên kết <a> trên trang
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        title_text = clean_text(a.get_text())
        
        # Tiêu đề tin tức hợp lệ thường dài trên 20 ký tự và không chứa từ khóa menu điều hướng
        if len(title_text) < 20:
            continue
            
        # Lọc bỏ các từ khóa điều hướng phổ biến
        exclude_keywords = ["trang chủ", "liên hệ", "giới thiệu", "sơ đồ", "đăng nhập", "đăng ký", "tìm kiếm", "rss"]
        if any(kw in title_text.lower() for kw in exclude_keywords):
            continue
            
        # Bỏ qua các liên kết neo hoặc javascript
        if href.startswith("#") or href.startswith("javascript:") or href.startswith("mailto:"):
            continue
            
        # Chuyển đổi thành đường dẫn tuyệt đối
        abs_url = urllib.parse.urljoin(base_url, href)
        
        # Chỉ lấy liên kết thuộc cùng tên miền của trang mục tiêu
        parsed_base = urllib.parse.urlparse(base_url)
        parsed_abs = urllib.parse.urlparse(abs_url)
        if parsed_abs.netloc != parsed_base.netloc:
            continue
            
        if abs_url not in seen_urls:
            seen_urls.add(abs_url)
            
            # Cố gắng tìm thẻ tóm tắt lân cận (sibling hoặc parent)
            summary_text = ""
            parent = a.find_parent()
            if parent:
                # Tìm thẻ đoạn văn hoặc div nhỏ lân cận chứa tóm tắt
                sibling_p = parent.find_next_sibling(["p", "div", "span"])
                if sibling_p:
                    summary_text = clean_text(sibling_p.get_text())[:200]
            
            articles.append({
                "title": title_text,
                "summary": summary_text or title_text, # Nếu không có tóm tắt thì dùng tiêu đề
                "url": abs_url,
                "published_date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            
    return articles

def parse_thanhtra_com_vn(html_content, base_url):
    """Bộ phân tích riêng cho Báo Thanh Tra"""
    soup = BeautifulSoup(html_content, "html.parser")
    articles = []
    
    # Cấu trúc của báo thường chứa tin trong class .story hoặc các thẻ article
    items = soup.select(".story, .item, .news-item, .post-item") or soup.find_all(["article", "section"])
    
    for item in items:
        a_tag = item.find("a", href=True)
        if not a_tag:
            continue
            
        href = a_tag["href"].strip()
        title_tag = item.find(["h2", "h3", "h4", "span"], class_=lambda c: c and ("title" in c or "heading" in c)) or a_tag
        title = clean_text(title_tag.get_text())
        
        if len(title) < 15:
            continue
            
        abs_url = urllib.parse.urljoin(base_url, href)
        
        # Tìm tóm tắt tin
        summary_tag = item.find(["p", "div", "span"], class_=lambda c: c and ("summary" in c or "sapo" in c or "desc" in c))
        summary = clean_text(summary_tag.get_text()) if summary_tag else ""
        
        articles.append({
            "title": title,
            "summary": summary or title,
            "url": abs_url,
            "published_date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
    return articles

def parse_thanhtra_hanoi_gov_vn(html_content, base_url):
    """Bộ phân tích riêng cho Thanh tra TP Hà Nội"""
    soup = BeautifulSoup(html_content, "html.parser")
    articles = []
    
    # Thanh tra Hà Nội thường hiển thị dạng bảng (kết luận thanh tra) hoặc danh sách tin tức
    rows = soup.select("table tr, .list-news .item, .news-item, .view-list li")
    
    for row in rows:
        a_tag = row.find("a", href=True)
        if not a_tag:
            continue
            
        href = a_tag["href"].strip()
        title = clean_text(a_tag.get_text())
        
        if len(title) < 15:
            continue
            
        abs_url = urllib.parse.urljoin(base_url, href)
        
        # Bóc tách ngày tháng nếu có trong hàng
        pub_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        date_span = row.find(["span", "td", "div"], class_=lambda c: c and ("date" in c or "time" in c))
        if date_span:
            pub_date = clean_text(date_span.get_text())
            
        articles.append({
            "title": title,
            "summary": title,
            "url": abs_url,
            "published_date": pub_date
        })
        
    return articles

def parse_thanhtra_gov_vn(html_content, base_url):
    """Bộ phân tích riêng cho Thanh tra Chính phủ (thanhtra.gov.vn)"""
    soup = BeautifulSoup(html_content, "html.parser")
    articles = []
    seen_urls = set()
    
    rows = soup.select("table tr")
    for row in rows:
        tds = row.find_all("td")
        if len(tds) < 4:
            continue
            
        a_tag = tds[2].find("a", href=True)
        if not a_tag or "_baiVietId=" not in a_tag["href"]:
            continue
            
        href = a_tag["href"].strip()
        title = clean_text(a_tag.get_text())
        if len(title) < 15:
            continue
            
        abs_url = urllib.parse.urljoin(base_url, href)
        if abs_url in seen_urls:
            continue
        seen_urls.add(abs_url)
        
        # Lấy ngày xuất bản từ cột 4 (tds[3])
        pub_date_str = clean_text(tds[3].get_text())
        pub_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if pub_date_str:
            try:
                parts = pub_date_str.split("/")
                if len(parts) == 3:
                    pub_date = f"{parts[2]}-{parts[1]}-{parts[0]} 00:00:00"
                else:
                    pub_date = pub_date_str
            except Exception:
                pass
                
        articles.append({
            "title": title,
            "summary": title,
            "url": abs_url,
            "published_date": pub_date
        })
        
    return articles

def parse_baotintuc_vn(html_content, base_url, session):
    """Bộ phân tích riêng cho Báo Tin Tức (phong-su-dieu-tra)"""
    soup = BeautifulSoup(html_content, "html.parser")
    articles = []
    seen_urls = set()
    
    # 1. Bóc tách bài nổi bật (Focus Item)
    newsest = soup.select_one(".newsest")
    if newsest:
        a_title = newsest.select_one("a.title")
        if a_title and a_title.get("href"):
            href = a_title["href"].strip()
            title = clean_text(a_title.get_text())
            abs_url = urllib.parse.urljoin(base_url, href)
            
            des_tag = newsest.select_one("p.des")
            summary = clean_text(des_tag.get_text()) if des_tag else ""
            
            seen_urls.add(abs_url)
            articles.append({
                "title": title,
                "summary": summary or title,
                "url": abs_url,
                "published_date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            
    # 2. Bóc tách danh sách các bài viết khác
    items = soup.select("ul.list-ul li.item, .list-news li, .list-news .item, .news-item")
    for item in items:
        a_title = item.select_one("a.title") or item.find("a", href=True)
        if not a_title or not a_title.get("href"):
            continue
            
        href = a_title["href"].strip()
        title = clean_text(a_title.get_text())
        
        if len(title) < 15:
            continue
            
        abs_url = urllib.parse.urljoin(base_url, href)
        if abs_url in seen_urls:
            continue
        seen_urls.add(abs_url)
        
        # Báo Tin Tức list view không chứa tóm tắt cho các bài viết phụ.
        # Ta sẽ cào nhanh trang chi tiết (giới hạn tối đa 8 bài mới nhất) để trích xuất sapo chính chủ.
        summary = ""
        try:
            if len(articles) < 8:
                # Tránh làm phiền server quá mức
                time.sleep(random.uniform(0.2, 0.7))
                r = session.get(abs_url, headers=get_headers(abs_url), timeout=10)
                if r.status_code == 200:
                    detail_soup = BeautifulSoup(r.text, 'html.parser')
                    sapo_tag = detail_soup.select_one(".sapo, h2.sapo, p.sapo, .desc-detail, .summary-detail")
                    if sapo_tag:
                        summary = clean_text(sapo_tag.get_text())
        except Exception as e:
            safe_print(f"[CANH BAO] Khong the lay sapo chi tiet cho {abs_url}: {e}")
            
        articles.append({
            "title": title,
            "summary": summary or title,
            "url": abs_url,
            "published_date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
    return articles

def parse_baophapluat_vn(html_content, base_url):
    """Bộ phân tích riêng cho Báo Pháp Luật Việt Nam (Bạn đọc đơn thư)"""
    soup = BeautifulSoup(html_content, "html.parser")
    articles = []
    seen_urls = set()
    
    # Báo Pháp luật có cấu trúc chứa bài trong các khối .story hoặc article
    items = soup.select(".story, article, .post, .article")
    
    for item in items:
        a_tag = item.find("a", href=True)
        if not a_tag:
            continue
            
        href = a_tag["href"].strip()
        title = clean_text(a_tag.get_text())
        if len(title) < 15:
            title_tag = item.find(["h2", "h3", "h4"])
            if title_tag:
                title = clean_text(title_tag.get_text())
                
        if len(title) < 15:
            continue
            
        abs_url = urllib.parse.urljoin(base_url, href)
        if abs_url in seen_urls:
            continue
        seen_urls.add(abs_url)
        
        # Tìm tóm tắt tin trong các thẻ mô tả lân cận
        summary_tag = item.find(["p", "div", "span"], class_=lambda c: c and ("summary" in c or "sapo" in c or "desc" in c or "lead" in c))
        if not summary_tag:
            # Lấy thẻ p bất kỳ có độ dài hợp lý lân cận
            p_tags = item.find_all("p")
            for p in p_tags:
                p_text = clean_text(p.get_text())
                if 20 < len(p_text) < 300:
                    summary_tag = p
                    break
                    
        summary = clean_text(summary_tag.get_text()) if summary_tag else ""
        
        articles.append({
            "title": title,
            "summary": summary or title,
            "url": abs_url,
            "published_date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
    return articles

def parse_baokiemtoan_vn(html_content, base_url):
    """Bộ phân tích riêng cho Báo Kiểm Toán (baokiemtoan.vn)"""
    soup = BeautifulSoup(html_content, "html.parser")
    articles = []
    seen_urls = set()
    
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if "/bai-viet/" in href:
            abs_url = urllib.parse.urljoin(base_url, href)
            if abs_url in seen_urls:
                continue
                
            title = clean_text(a.get_text())
            if not title:
                img = a.find("img")
                if img and img.get("alt"):
                    title = clean_text(img["alt"])
            
            if len(title) < 15:
                continue
                
            seen_urls.add(abs_url)
            articles.append({
                "title": title,
                "summary": title,
                "url": abs_url,
                "published_date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            
    return articles

def parse_laodong_vn(html_content, base_url):
    """Bộ phân tích riêng cho Báo Lao Động"""
    soup = BeautifulSoup(html_content, "html.parser")
    articles = []
    seen_urls = set()
    
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.endswith(".ldo"):
            abs_url = urllib.parse.urljoin(base_url, href)
            if abs_url in seen_urls:
                continue
                
            title = clean_text(a.get_text())
            if not title:
                img = a.find("img")
                if img and img.get("alt"):
                    title = clean_text(img["alt"])
            
            if len(title) < 15:
                continue
                
            seen_urls.add(abs_url)
            
            summary = ""
            parent = a.find_parent()
            if parent:
                desc_tag = parent.find_next_sibling(["p", "div", "span"])
                if desc_tag:
                    summary = clean_text(desc_tag.get_text())[:200]
                    
            articles.append({
                "title": title,
                "summary": summary or title,
                "url": abs_url,
                "published_date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            
    return articles

def parse_thanhnien_vn(html_content, base_url):
    """Bộ phân tích riêng cho Báo Thanh Niên"""
    soup = BeautifulSoup(html_content, "html.parser")
    articles = []
    seen_urls = set()
    
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if re.search(r'-\d{8,}\.htm$', href):
            abs_url = urllib.parse.urljoin(base_url, href)
            if abs_url in seen_urls:
                continue
                
            title = clean_text(a.get_text())
            if not title:
                img = a.find("img")
                if img and img.get("alt"):
                    title = clean_text(img["alt"])
                    
            if len(title) < 15:
                continue
                
            seen_urls.add(abs_url)
            
            summary = ""
            parent = a.find_parent()
            if parent:
                desc_tag = parent.find_next_sibling(["p", "div", "span"])
                if desc_tag:
                    summary = clean_text(desc_tag.get_text())[:200]
                    
            articles.append({
                "title": title,
                "summary": summary or title,
                "url": abs_url,
                "published_date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            
    return articles

def parse_tuoitre_vn(html_content, base_url):
    """Bộ phân tích riêng cho Báo Tuổi Trẻ"""
    soup = BeautifulSoup(html_content, "html.parser")
    articles = []
    seen_urls = set()
    
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if re.search(r'-\d{8,}\.htm$', href):
            abs_url = urllib.parse.urljoin(base_url, href)
            if abs_url in seen_urls:
                continue
                
            title = clean_text(a.get_text())
            if not title:
                img = a.find("img")
                if img and img.get("alt"):
                    title = clean_text(img["alt"])
                    
            if len(title) < 15:
                continue
                
            seen_urls.add(abs_url)
            
            summary = ""
            parent = a.find_parent()
            if parent:
                desc_tag = parent.find_next_sibling(["p", "div", "span"])
                if desc_tag:
                    summary = clean_text(desc_tag.get_text())[:200]
                    
            articles.append({
                "title": title,
                "summary": summary or title,
                "url": abs_url,
                "published_date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            
    return articles

def parse_baoxaydung_vn(html_content, base_url):
    """Bộ phân tích riêng cho Báo Xây Dựng"""
    soup = BeautifulSoup(html_content, "html.parser")
    articles = []
    seen_urls = set()
    
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if re.search(r'-\d{8,}\.htm$', href):
            abs_url = urllib.parse.urljoin(base_url, href)
            if abs_url in seen_urls:
                continue
                
            title = clean_text(a.get_text())
            if not title:
                img = a.find("img")
                if img and img.get("alt"):
                    title = clean_text(img["alt"])
            
            if len(title) < 15:
                continue
                
            seen_urls.add(abs_url)
            
            summary = ""
            parent = a.find_parent()
            if parent:
                desc_tag = parent.find_next_sibling(["p", "div", "span"])
                if desc_tag:
                    summary = clean_text(desc_tag.get_text())[:200]
                    
            articles.append({
                "title": title,
                "summary": summary or title,
                "url": abs_url,
                "published_date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            
    return articles

def scrape_non_rss_source(source):
    """Xử lý cào một nguồn phi RSS cụ thể"""
    name = source["source_name"]
    url = source["rss_url"]  # Cột rss_url lưu URL chính của trang cào
    category = source["category"]
    
    safe_print(f"\n[TIM KIEM] Dang cao nguon HTML truc tiep: {name} ({url})...")
    
    try:
        # Gửi request tải trang web thông qua requests.Session với LegacySSLAdapter
        session = requests.Session()
        session.mount("https://", LegacySSLAdapter())
        session.mount("http://", LegacySSLAdapter())
        
        response = session.get(url, headers=get_headers(url), timeout=20, verify=False)
        response.encoding = 'utf-8' # Đảm bảo đọc đúng font tiếng Việt
        
        # Tự động vượt qua cookie-challenge đặc thù của Báo Lao Động (laodong.vn)
        parsed_url = urllib.parse.urlparse(url)
        domain = parsed_url.netloc.lower()
        if "laodong.vn" in domain and 'document.cookie="' in response.text:
            import re
            cookie_match = re.search(r'document\.cookie="([^=]+)=([^"]+)"', response.text)
            if cookie_match:
                cookie_name = cookie_match.group(1)
                cookie_value = cookie_match.group(2).split(";")[0]
                session.cookies.set(cookie_name, cookie_value, domain="laodong.vn")
                # Tải lại trang sau khi đã thiết lập Cookie
                response = session.get(url, headers=get_headers(url), timeout=20, verify=False)
                response.encoding = 'utf-8'
        
        if response.status_code != 200:
            safe_print(f"[LOI] Khong the tai trang. Ma trang thai HTTP: {response.status_code}")
            return []
            
        html = response.text
        articles = []
        
        # Điều hướng phân tích theo từng tên miền cụ thể
        if "thanhtra.com.vn" in domain:
            articles = parse_thanhtra_com_vn(html, url)
        elif "thanhtra.hanoi.gov.vn" in domain:
            articles = parse_thanhtra_hanoi_gov_vn(html, url)
        elif "thanhtra.gov.vn" in domain:
            articles = parse_thanhtra_gov_vn(html, url)
        elif "baotintuc.vn" in domain:
            articles = parse_baotintuc_vn(html, url, session)
        elif "baophapluat.vn" in domain:
            articles = parse_baophapluat_vn(html, url)
        elif "baokiemtoan.vn" in domain:
            articles = parse_baokiemtoan_vn(html, url)
        elif "laodong.vn" in domain:
            articles = parse_laodong_vn(html, url)
        elif "thanhnien.vn" in domain:
            articles = parse_thanhnien_vn(html, url)
        elif "tuoitre.vn" in domain:
            articles = parse_tuoitre_vn(html, url)
        elif "baoxaydung.vn" in domain:
            articles = parse_baoxaydung_vn(html, url)
        else:
            # Dành cho các cổng sở ngành Hà Nội dùng chung nền tảng DNN
            articles = parse_thanhtra_hanoi_gov_vn(html, url)
            
        # Nếu bộ phân tích chuyên dụng không tìm thấy bài nào, kích hoạt Smart Fallback Extractor
        if not articles:
            safe_print("[CANH BAO] Bo phan tich chuyen dung khong co ket qua. Kich hoat bo boc tach du phong thong minh...")
            articles = smart_fallback_extractor(html, url)
            
        # Chuẩn hóa định dạng trước khi lưu vào DB
        final_articles = []
        for art in articles:
            final_articles.append({
                "source_type": "custom_scraper",
                "source_name": name,
                "title": art["title"],
                "url": art["url"],
                "summary": art["summary"] or art["title"],
                "published_date": art["published_date"]
            })
            
        safe_print(f"[OK] Boc tach thanh cong {len(final_articles)} tin bài tu {name}.")
        return final_articles
        
    except Exception as e:
        safe_print(f"[LOI] Loi xay ra trong qua trinh cao {name}: {e}")
        return []

def fetch_single_article_summary(article):
    """Tải và trích xuất tóm tắt cho một bài báo bằng newspaper4k"""
    url = article.get('url')
    if not url:
        return
    try:
        from newspaper import Article, Config
        config = Config()
        config.language = 'vi'
        config.request_timeout = 8
        config.max_summary_sent = 7  # Tăng số câu tóm tắt lên 7 câu
        # Giả lập User-Agent trình duyệt tối ưu để tránh bị bóp băng thông
        config.user_agent = get_headers(url)["User-Agent"]
        
        art = Article(url, config=config)
        art.download()
        if not art.html:
            return
        art.parse()
        art.nlp()
        summary = art.summary.strip()
        if summary:
            article['summary'] = " ".join(summary.split())
            safe_print(f"🟢 Đã tóm tắt bằng 4k: {article['title'][:45]}...")
        elif art.text:
            # Fallback nếu NLP summary trống nhưng có text
            snippet = " ".join(art.text.split()[:50]) + "..."
            article['summary'] = snippet
            safe_print(f"🟢 Đã tóm tắt bằng 4k (lấy đoạn ngắn): {article['title'][:45]}...")
    except Exception:
        pass

def process_domain_group(domain, group_sources):
    """Cào tuần tự các nguồn thuộc cùng một tên miền để đảm bảo tính lịch sự"""
    group_articles = []
    for idx, source in enumerate(group_sources):
        articles = scrape_non_rss_source(source)
        if articles:
            group_articles.extend(articles)
        
        # Chỉ delay nếu còn nguồn tiếp theo trong cùng domain
        if idx < len(group_sources) - 1:
            delay = random.uniform(1.5, 3.0)
            safe_print(f"[DELAY] Dang nghi {delay:.1f} giay trong domain {domain}...")
            time.sleep(delay)
            
    return group_articles

def main():
    import time
    from collections import defaultdict
    from urllib.parse import urlparse
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    start_time = time.time()
    safe_print("=== BAT DAU CHAY PIPELINE CAO HTML TRUC TIEP TOI UU (NON-RSS SCRAPING) ===")
    
    # 1. Lấy danh sách nguồn phi RSS đang hoạt động trong DB
    sources = get_active_non_rss_sources()
    safe_print(f"-> Tim thay {len(sources)} nguon cao HTML truc tiep trong he thong.")
    
    # 2. Gom nhóm theo domain
    domain_groups = defaultdict(list)
    for src in sources:
        domain = urlparse(src["rss_url"]).netloc.lower()
        domain_groups[domain].append(src)
        
    safe_print(f"⚡ Đã gom cụm thành {len(domain_groups)} nhóm tên miền riêng biệt.")
    
    all_raw_articles = []
    
    # 3. Song song hóa việc cào giữa các tên miền khác nhau
    safe_print(f"🚀 Đang cào song song {len(domain_groups)} nhóm tên miền bằng 8 luồng...")
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(process_domain_group, domain, group_sources): domain 
            for domain, group_sources in domain_groups.items()
        }
        
        for future in as_completed(futures):
            domain = futures[future]
            try:
                articles = future.result()
                if articles:
                    all_raw_articles.extend(articles)
            except Exception as e:
                safe_print(f"❌ Nhóm tên miền {domain} gặp lỗi: {e}")
                
    total_saved = 0
    # 4. Lọc trùng lặp một lần duy nhất
    if all_raw_articles:
        safe_print(f"\n🔍 Dang kiem tra {len(all_raw_articles)} bai viet thu thap duoc voi CSDL...")
        urls = [art['url'] for art in all_raw_articles if art.get('url')]
        new_urls = filter_new_urls(urls)
        
        # Chỉ giữ lại những bài thực sự mới
        new_articles = []
        seen = set()
        for art in all_raw_articles:
            url = art.get('url')
            if url in new_urls and url not in seen:
                seen.add(url)
                new_articles.append(art)
        
        if new_articles:
            safe_print(f"📝 Phát hiện {len(new_articles)} bài viết mới hoàn toàn trên toàn hệ thống.")
            safe_print("⚡ Đang trích xuất tóm tắt chuyên sâu song song (15 luồng Newspaper4k)...")
            
            with ThreadPoolExecutor(max_workers=15) as summary_executor:
                summary_futures = [summary_executor.submit(fetch_single_article_summary, art) for art in new_articles]
                for future in as_completed(summary_futures):
                    try:
                        future.result()
                    except Exception:
                        pass
                        
            # Lưu hàng loạt vào DB
            total_saved = save_articles(new_articles)
            safe_print(f"\n🎉 HOÀN THÀNH: Đã lưu {total_saved} bài viết mới vào DB.")
        else:
            safe_print("\n✨ Khong co bai viet moi nao can xu ly them.")
    else:
        safe_print("\n⚠️ Không cào được bài viết nào từ các nguồn.")
        
    elapsed = time.time() - start_time
    safe_print(f"\n=== HOAN THANH CAO TOAN BO NGUON PHI RSS ===")
    safe_print(f"   - Tong so tin bai moi duoc ghi nhan thanh cong: {total_saved} bai.")
    safe_print(f"   - Tong thoi gian chay pipeline: {elapsed:.2f} giay.")

if __name__ == "__main__":
    main()
