# -*- coding: utf-8 -*-
"""
google_fake.py (Bản Nâng Cấp - Quét Live RSS thực tế từ Database)
=============================================================================
Tự động truy vấn CSDL crawler_data.db để tìm các nguồn RSS của:
- Hà Nội Mới (hanoimoi.vn)
- Kinh tế Môi trường (kinhtemoitruong.vn)
- Quân đội Nhân dân (qdnd.vn)
Sau đó tải live bài viết mới nhất từ RSS và chạy kiểm thử song song hai phương pháp:
1. Cào trực tiếp (Không proxy - xem có bị chặn không)
2. Cào qua bộ lưu đệm Google Web Cache
=============================================================================
"""

import os
import sys
import sqlite3
import urllib.parse
import requests
import feedparser
from bs4 import BeautifulSoup

# Đảm bảo in tiếng Việt chuẩn trên Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

def get_latest_url_from_rss(rss_url):
    """Tải RSS và trích xuất URL bài viết mới nhất"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        r = requests.get(rss_url, headers=headers, timeout=10)
        if r.status_code == 200:
            feed = feedparser.parse(r.text)
            if feed.entries:
                entry = feed.entries[0]
                return entry.get('link'), entry.get('title', 'Không có tiêu đề')
    except Exception as e:
        print(f"   ❌ Lỗi tải RSS {rss_url}: {e}")
    return None, None

def fetch_direct(url):
    """Cào trực tiếp xem có bị chặn IP nước ngoài không"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "vi-VN,vi;q=0.9",
    }
    try:
        r = requests.get(url, headers=headers, timeout=8)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'lxml')
            title = soup.title.string.strip() if soup.title else "Không có tiêu đề"
            print(f"   🟢 [TRỰC TIẾP] Thành công (Status 200). Tiêu đề: {title[:50]}... | Dung lượng: {len(r.text)} ký tự")
            return True
        else:
            print(f"   🔴 [TRỰC TIẾP] BỊ CHẶN (Status {r.status_code})")
            return False
    except Exception as e:
        print(f"   🔴 [TRỰC TIẾP] Thất bại (Lỗi kết nối: {type(e).__name__})")
        return False

def fetch_via_google_cache(url):
    """Cào thông qua cổng Google Web Cache"""
    cache_url = f"https://webcache.googleusercontent.com/search?q=cache:{url}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "vi-VN,vi;q=0.9",
        "Referer": "https://www.google.com/"
    }
    try:
        r = requests.get(cache_url, headers=headers, timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'lxml')
            title = soup.title.string.strip() if soup.title else "Không có tiêu đề"
            title = title.replace(" - Bản lưu", "").replace(" - Google Cache", "")
            
            # Trích xuất thử đoạn text đầu tiên
            paragraphs = [p.get_text().strip() for p in soup.find_all('p') if len(p.get_text().strip()) > 30]
            snippet = paragraphs[0][:75] + "..." if paragraphs else "Không trích xuất được văn bản"
            
            print(f"   🎉 [GOOGLE CACHE] VƯỢT RÀO THÀNH CÔNG (Status 200) | Tiêu đề: {title[:50]}...")
            print(f"      👉 Đoạn trích: \"{snippet}\"")
            return True
        elif r.status_code == 404:
            print(f"   ⚠️  [GOOGLE CACHE] Thất bại (Lỗi 404: Google chưa kịp lưu trang này vào Cache)")
            return False
        else:
            print(f"   🔴 [GOOGLE CACHE] Bị chặn hoặc yêu cầu Captcha (Status {r.status_code})")
            return False
    except Exception as e:
        print(f"   🔴 [GOOGLE CACHE] Thất bại (Lỗi kết nối: {type(e).__name__})")
        return False

def main():
    print("================================================================================")
    print("🚀 BẮT ĐẦU LIVE TEST TRÊN NGUỒN RSS CỦA HANOIMOI, KINHTEMOITRUONG, QDND 🚀")
    print("================================================================================\n")
    
    # 1. Kết nối CSDL để tìm RSS feed
    conn = sqlite3.connect('crawler_data.db')
    cur = conn.cursor()
    
    targets = {
        "hanoimoi": {
            "name": "Hà Nội Mới",
            "keyword": "%hanoimoi%",
            "default_rss": "https://hanoimoi.vn/rss/thoi-su.rss"
        },
        "kinhtemoitruong": {
            "name": "Kinh tế Môi trường",
            "keyword": "%kinhtemoitruong%",
            "default_rss": "https://kinhtemoitruong.vn/rss/moi-truong-24h-1.rss"
        },
        "qdnd": {
            "name": "Quân đội Nhân dân",
            "keyword": "%qdnd%",
            "default_rss": "https://www.qdnd.vn/rss/cate/tin-tuc-moi-nhat.rss"
        }
    }
    
    for key, info in targets.items():
        print(f"📌 ĐANG RÀ SOÁT NGUỒN: {info['name'].upper()}")
        
        # Tìm RSS url trong DB
        cur.execute("SELECT rss_url FROM rss_sources WHERE rss_url LIKE ? LIMIT 1", (info['keyword'],))
        row = cur.fetchone()
        rss_url = row[0] if row else info['default_rss']
        
        print(f"   🔍 Tìm thấy RSS URL: {rss_url}")
        print(f"   🔄 Đang tải bài viết mới nhất từ RSS này...")
        
        url, title = get_latest_url_from_rss(rss_url)
        
        if not url:
            print(f"   ❌ Không thể trích xuất bài viết nào từ RSS này. Chuyển sang nguồn kế tiếp.\n")
            continue
            
        print(f"   📰 Bài viết mới phát hiện: \"{title}\"")
        print(f"   🔗 Link gốc: {url}")
        
        # Chạy kiểm thử so sánh
        fetch_direct(url)
        fetch_via_google_cache(url)
        print("-" * 80 + "\n")
        
    conn.close()
    print("================================================================================")
    print("🎉 HOÀN THÀNH QUY TRÌNH KIỂM THỬ LIVE!")
    print("================================================================================")

if __name__ == "__main__":
    main()
