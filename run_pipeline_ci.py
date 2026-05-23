"""
run_pipeline_ci.py — Pipeline CI cho GitHub Actions
=====================================================
Phiên bản mới: Kết nối trực tiếp Render Postgres (không dùng Telegram làm DB storage).

Dùng --report-only để chỉ gửi báo cáo thống kê lên Telegram mà không chạy lại crawler.
"""
import os
import sys
import argparse
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Đảm bảo in tiếng Việt
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Import db_adapter để hỗ trợ cả SQLite và PostgreSQL
import db_adapter

# 12 Lĩnh vực bảo vệ
DOMAINS = {
    1: "Trẻ em", 2: "Người cao tuổi", 3: "Người khuyết tật",
    4: "Phụ nữ mang thai/nuôi con nhỏ", 5: "Dân tộc thiểu số",
    6: "Người mất năng lực hành vi", 7: "Đầu tư công",
    8: "Đất đai/Tài sản công", 9: "Môi trường",
    10: "Di sản văn hóa", 11: "An toàn thực phẩm/Dược phẩm",
    12: "Người tiêu dùng"
}


def get_stats_before() -> int:
    """Lấy tổng số bài báo thô hiện có trong DB."""
    try:
        conn = db_adapter.get_conn()
        cur = db_adapter.dict_cursor(conn)
        cur.execute("SELECT COUNT(*) AS cnt FROM raw_articles")
        row = cur.fetchone()
        conn.close()
        return int(row["cnt"]) if row else 0
    except Exception as e:
        print(f"⚠️ Lỗi đọc stats: {e}")
        return 0


def get_pipeline_stats(pre_count: int, start_time: datetime) -> dict:
    """Thống kê kết quả sau mỗi lần chạy pipeline."""
    stats = {"new_articles": 0, "ai_sent": 0, "ai_matched": 0, "matched_details": {}}
    try:
        conn = db_adapter.get_conn()
        cur = db_adapter.dict_cursor(conn)
        p = db_adapter.ph()

        # Bài mới cào được
        cur.execute("SELECT COUNT(*) AS cnt FROM raw_articles")
        post_count = int(cur.fetchone()["cnt"])
        stats["new_articles"] = max(0, post_count - pre_count)

        # Bài AI đã thẩm định trong đợt này
        start_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
        if db_adapter.is_postgres():
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM classified_articles WHERE classified_at >= %s::timestamp",
                (start_str,)
            )
        else:
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM classified_articles WHERE datetime(classified_at) >= datetime(?)",
                (start_str,)
            )
        stats["ai_sent"] = int(cur.fetchone()["cnt"])

        # Bài khớp theo lĩnh vực
        if db_adapter.is_postgres():
            cur.execute(
                "SELECT domain_id, COUNT(*) AS cnt FROM classified_articles "
                "WHERE domain_id > 0 AND classified_at >= %s::timestamp GROUP BY domain_id",
                (start_str,)
            )
        else:
            cur.execute(
                "SELECT domain_id, COUNT(*) AS cnt FROM classified_articles "
                "WHERE domain_id > 0 AND datetime(classified_at) >= datetime(?) GROUP BY domain_id",
                (start_str,)
            )
        total_matched = 0
        for row in cur.fetchall():
            dom_id = int(row["domain_id"])
            count  = int(row["cnt"])
            name   = DOMAINS.get(dom_id, f"Lĩnh vực {dom_id}")
            stats["matched_details"][name] = count
            total_matched += count
        stats["ai_matched"] = total_matched
        conn.close()
    except Exception as e:
        print(f"⚠️ Lỗi truy vấn thống kê: {e}")
    return stats


def send_telegram_report(bot_token: str, chat_id: str, stats: dict):
    """Gửi báo cáo tóm tắt lên Telegram."""
    import requests

    detail_lines = ""
    for domain_name, count in stats.get("matched_details", {}).items():
        detail_lines += f"   • {domain_name}: {count} bài\n"
    if not detail_lines:
        detail_lines = "   (Không có bài vi phạm mới)\n"

    db_mode = "🐘 PostgreSQL" if db_adapter.is_postgres() else "🗄️ SQLite"
    now_vn = datetime.utcnow()

    message = (
        "🏛️ **BÁO CÁO TỰ ĐỘNG - VKS BOT PIPELINE** 🏛️\n"
        "──────────────────────────\n"
        f"🕐 Thời gian: {now_vn.strftime('%d/%m/%Y %H:%M')} UTC\n"
        f"💾 Database: {db_mode}\n"
        "──────────────────────────\n"
        f"📰 Bài báo cào mới: **{stats['new_articles']}** bài\n"
        f"🤖 Bài AI thẩm định: **{stats['ai_sent']}** bài\n"
        f"⚠️ Phát hiện vi phạm: **{stats['ai_matched']}** bài\n"
        "──────────────────────────\n"
        "📊 **Chi tiết theo lĩnh vực**:\n"
        f"{detail_lines}"
        "──────────────────────────\n"
        "✅ Pipeline hoàn thành!"
    )

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }, timeout=15)
        if resp.status_code == 200:
            print("📨 Đã gửi báo cáo lên Telegram thành công!")
        else:
            print(f"⚠️ Lỗi gửi Telegram: {resp.text}")
    except Exception as e:
        print(f"⚠️ Không thể gửi Telegram: {e}")


def main():
    parser = argparse.ArgumentParser(description="VKS BOT CI Pipeline")
    parser.add_argument("--report-only", action="store_true",
                        help="Chỉ gửi báo cáo Telegram, không chạy crawler")
    args = parser.parse_args()

    print("🚀 BẮT ĐẦU VKS BOT CI PIPELINE (Render Postgres + GitHub Actions)")
    print(f"   📡 Database mode: {'PostgreSQL' if db_adapter.is_postgres() else 'SQLite'}")

    bot_token = os.getenv("TELEGRAM_BOT")
    chat_id   = os.getenv("TELEGRAM_CHAT_ID")

    start_time = datetime.utcnow()
    pre_count = get_stats_before()
    print(f"📊 Số bài hiện có trong DB: {pre_count}")

    if not args.report_only:
        # Bước 1: Khởi tạo DB schema
        print("\n--- BƯỚC 1: KHỞI TẠO DATABASE ---")
        from crawler_db_github import init_db
        init_db()

        # Bước 2: Crawler RSS
        print("\n--- BƯỚC 2: CÀO TIN RSS ---")
        try:
            import test_crawler_github
            test_crawler_github.main()
        except Exception as e:
            print(f"❌ Lỗi crawler RSS: {e}")

        # Bước 3: Crawler Non-RSS
        print("\n--- BƯỚC 3: CÀO TIN NON-RSS ---")
        try:
            import non_rss_scraper_github
            non_rss_scraper_github.main()
        except Exception as e:
            print(f"❌ Lỗi crawler Non-RSS: {e}")

        # Bước 4: Phân loại AI
        print("\n--- BƯỚC 4: PHÂN LOẠI AI ---")
        try:
            import classifier_api_github
            classifier_api_github.main()
        except Exception as e:
            print(f"❌ Lỗi AI Classifier: {e}")

    # Bước 5: Thống kê và báo cáo
    print("\n--- BƯỚC 5: BÁO CÁO KẾT QUẢ ---")
    stats = get_pipeline_stats(pre_count, start_time)
    print(f"   ✅ Bài mới: {stats['new_articles']}")
    print(f"   🤖 AI thẩm định: {stats['ai_sent']}")
    print(f"   ⚠️ Vi phạm: {stats['ai_matched']}")

    if bot_token and chat_id:
        send_telegram_report(bot_token, chat_id, stats)
    else:
        print("⚠️ Thiếu TELEGRAM_BOT hoặc TELEGRAM_CHAT_ID — bỏ qua gửi báo cáo.")

    print("\n🎉 Pipeline hoàn thành!")


if __name__ == "__main__":
    main()
