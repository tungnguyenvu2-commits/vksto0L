import os
import sys
import requests
from datetime import datetime

# Đảm bảo in tiếng Việt chuẩn trên Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

def download_db(bot_token, chat_id, dest_path="crawler_data.db"):
    """
    Tải file database SQLite mới nhất từ tin nhắn đã ghim trong chat/channel Telegram.
    Trả về True nếu thành công, False nếu thất bại.
    """
    print(f"📥 Đang tìm kiếm cơ sở dữ liệu đã ghim tại chat/channel: {chat_id}...")
    
    # 1. Lấy thông tin chat để tìm tin nhắn đã ghim (pinned_message)
    get_chat_url = f"https://api.telegram.org/bot{bot_token}/getChat"
    try:
        resp = requests.post(get_chat_url, json={"chat_id": chat_id}, timeout=20)
        resp_data = resp.json()
        
        if not resp_data.get("ok"):
            print(f"❌ Không thể truy cập chat/channel: {resp_data.get('description')}")
            return False
            
        chat_info = resp_data.get("result", {})
        pinned_msg = chat_info.get("pinned_message")
        
        if not pinned_msg:
            print("⚠️ Cảnh báo: Không tìm thấy tin nhắn đã ghim nào trong chat này!")
            print("💡 Nếu đây là lần chạy đầu tiên, hệ thống sẽ tự động khởi tạo database mới.")
            return False
            
        document = pinned_msg.get("document")
        if not document:
            print("❌ Tin nhắn được ghim không chứa tệp tin (document)!")
            return False
            
        file_name = document.get("file_name", "")
        file_id = document.get("file_id")
        
        print(f"🗄️ Đã phát hiện tệp tin đã ghim: '{file_name}' (ID: {file_id[:15]}...)")
        
        # 2. Lấy đường dẫn tải file (file_path) từ Telegram
        get_file_url = f"https://api.telegram.org/bot{bot_token}/getFile"
        file_resp = requests.post(get_file_url, json={"file_id": file_id}, timeout=20)
        file_data = file_resp.json()
        
        if not file_data.get("ok"):
            print(f"❌ Lỗi lấy thông tin file từ Telegram: {file_data.get('description')}")
            return False
            
        file_path = file_data.get("result", {}).get("file_path")
        if not file_path:
            print("❌ Không lấy được đường dẫn file_path từ Telegram.")
            return False
            
        # 3. Tải tệp tin thực tế về
        download_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
        print(f"⚡ Đang tải cơ sở dữ liệu từ Telegram...")
        
        r = requests.get(download_url, stream=True, timeout=60)
        if r.status_code == 200:
            with open(dest_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"✅ Tải database thành công và lưu tại: {dest_path} ({os.path.getsize(dest_path)} bytes)")
            return True
        else:
            print(f"❌ Tải file thất bại, HTTP status: {r.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Lỗi kết nối khi tải database: {e}")
        return False

def upload_db(bot_token, chat_id, db_path="crawler_data.db"):
    """
    Upload file database SQLite lên chat/channel Telegram và ghim tệp tin này lại.
    Trả về True nếu thành công, False nếu thất bại.
    """
    if not os.path.exists(db_path):
        print(f"❌ Lỗi: File database không tồn tại ở đường dẫn: {db_path}")
        return False
        
    file_size_mb = os.path.getsize(db_path) / (1024 * 1024)
    print(f"📤 Đang chuẩn bị tải lên database '{db_path}' ({file_size_mb:.2f} MB)...")
    
    if file_size_mb > 49.0:
        print("⚠️ Cảnh báo: Kích thước file vượt quá 50MB (giới hạn của Telegram Bot API).")
        # Trong tương lai có thể bổ sung nén zip nếu cần.
        
    # 1. Gửi file đính kèm qua sendDocument
    send_doc_url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        with open(db_path, "rb") as f:
            files = {"document": (f"crawler_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db", f)}
            data = {
                "chat_id": chat_id,
                "caption": f"🗄️ CƠ SỞ DỮ LIỆU VKS_BOT (BACKUP TỰ ĐỘNG)\n⏰ Thời gian: {timestamp}\n💾 Kích thước: {file_size_mb:.2f} MB"
            }
            resp = requests.post(send_doc_url, data=data, files=files, timeout=120)
            resp_data = resp.json()
            
        if not resp_data.get("ok"):
            print(f"❌ Tải lên database thất bại: {resp_data.get('description')}")
            return False
            
        message_id = resp_data.get("result", {}).get("message_id")
        print(f"✅ Đã gửi database lên Telegram thành công (Message ID: {message_id})")
        
        # 2. Ghim tin nhắn mới này lại để các lần chạy sau tìm thấy
        pin_url = f"https://api.telegram.org/bot{bot_token}/pinChatMessage"
        pin_resp = requests.post(pin_url, json={
            "chat_id": chat_id,
            "message_id": message_id,
            "disable_notification": True
        }, timeout=20)
        
        if pin_resp.json().get("ok"):
            print("📌 Ghim cơ sở dữ liệu mới thành công!")
            return True
        else:
            print(f"⚠️ Không thể ghim tin nhắn mới: {pin_resp.json().get('description')}")
            return False
            
    except Exception as e:
        print(f"❌ Lỗi kết nối khi tải lên database: {e}")
        return False

def send_summary_report(bot_token, chat_id, stats_summary):
    """
    Gửi báo cáo tóm tắt tiến trình cào và phân loại về Telegram chat/channel.
    """
    print("📊 Đang gửi báo cáo tóm tắt lên Telegram...")
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = (
        "🤖 **BÁO CÁO PIPELINE TỰ ĐỘNG VKS_BOT** 🤖\n"
        "──────────────────────────\n"
        f"⏰ **Thời gian chạy**: {timestamp}\n"
        f"🔄 **Tổng tin cào mới**: {stats_summary.get('new_articles', 0)} bài\n"
        f"🔍 **Tổng tin gửi AI**: {stats_summary.get('ai_sent', 0)} bài\n"
        f"🚨 **Phát hiện dấu hiệu vi phạm**: {stats_summary.get('ai_matched', 0)} bài\n"
        "──────────────────────────\n"
    )
    
    if stats_summary.get("matched_details"):
        message += "📌 **Lĩnh vực vi phạm phát hiện mới**:\n"
        for domain_name, count in stats_summary["matched_details"].items():
            message += f" └─ `{domain_name}`: {count} bài\n"
        message += "──────────────────────────\n"
        
    message += "🟢 Trạng thái hệ thống: **HOẠT ĐỘNG TỐT**"
    
    try:
        requests.post(url, json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }, timeout=20)
        print("✅ Gửi báo cáo tóm tắt thành công!")
    except Exception as e:
        print(f"⚠️ Gửi báo cáo tóm tắt thất bại: {e}")

if __name__ == "__main__":
    # Test script offline
    if len(sys.argv) > 3:
        action = sys.argv[1]
        token = sys.argv[2]
        cid = sys.argv[3]
        if action == "download":
            download_db(token, cid)
        elif action == "upload":
            upload_db(token, cid)
