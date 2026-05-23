import os
import json
import re
import sqlite3
import time
import random
from dotenv import load_dotenv
import google.generativeai as genai
from concurrent.futures import ThreadPoolExecutor, as_completed

# Đảm bảo in tiếng Việt chuẩn trên Windows bằng reconfigure
import sys
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Tải biến môi trường từ file .env
load_dotenv()

# Tự động chuyển hướng kết nối sang PostgreSQL nếu có DATABASE_URL và đang ở môi trường Deploy (Render/GitHub Actions)
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
        if database == "crawler_data.db" or "crawler_data.db" in str(database):
            pg_conn = psycopg2.connect(os.getenv("DATABASE_URL"))
            return PGConnWrapper(pg_conn)
        return original_sqlite_connect(database, *args, **kwargs)
    sqlite3.connect = custom_connect

DB_FILE = "crawler_data.db"

# 12 Lĩnh Vực Bảo Vệ theo Nghị quyết số 205/2025/QH15
DOMAINS = {
    1: {"name": "Nhóm dễ bị tổn thương: Trẻ em"},
    2: {"name": "Nhóm dễ bị tổn thương: Người cao tuổi"},
    3: {"name": "Nhóm dễ bị tổn thương: Người khuyết tật"},
    4: {"name": "Nhóm dễ bị tổn thương: Phụ nữ mang thai / Nuôi con dưới 36 tháng"},
    5: {"name": "Nhóm dễ bị tổn thương: Dân tộc thiểu số vùng ĐBKK"},
    6: {"name": "Nhóm dễ bị tổn thương: Người khó khăn nhận thức / Mất năng lực hành vi"},
    7: {"name": "Lợi ích công: Đầu tư công"},
    8: {"name": "Lợi ích công: Tài sản công, Đất đai"},
    9: {"name": "Lợi ích công: Môi trường, Hệ sinh thái"},
    10: {"name": "Lợi ích công: Di sản văn hóa"},
    11: {"name": "Lợi ích công: An toàn thực phẩm, Dược phẩm"},
    12: {"name": "Lợi ích công: Bảo vệ quyền lợi người tiêu dùng"}
}

# --- LỚP 2: BỘ LỌC TINH BẰNG GEMINI 1.5 FLASH ---
def robust_json_loads(raw_text):
    """Làm sạch và parse JSON siêu mạnh mẽ từ phản hồi của Gemma (sửa dấu phẩy thừa, nháy đơn, boolean Python...)"""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\n", "", cleaned)
        cleaned = re.sub(r"\n```$", "", cleaned)
    
    # 1. Trích xuất mảng JSON [...]
    start = cleaned.find('[')
    end = cleaned.rfind(']')
    if start != -1 and end != -1 and start < end:
        cleaned = cleaned[start:end+1]
        
    # 2. Thay nháy đơn thành nháy kép
    cleaned = cleaned.replace("'", '"')
    
    # 3. Thay Python Booleans và None sang JSON
    cleaned = cleaned.replace("True", "true").replace("False", "false").replace("None", "null")
    
    # 4. Sửa các dấu phẩy thừa trước ngoặc đóng
    cleaned = re.sub(r',\s*}', '}', cleaned)
    cleaned = re.sub(r',\s*\]', ']', cleaned)
    
    try:
        return json.loads(cleaned)
    except Exception as parse_err:
        # Cách bóc tách cấp cứu: tìm từng dictionary dạng { ... } bằng Regex
        try:
            objects = []
            dict_strings = re.findall(r'\{[^{}]+\}', cleaned)
            for ds in dict_strings:
                try:
                    ds_clean = ds.replace("'", '"')
                    ds_clean = ds_clean.replace("True", "true").replace("False", "false").replace("None", "null")
                    ds_clean = re.sub(r',\s*}', '}', ds_clean)
                    objects.append(json.loads(ds_clean))
                except Exception:
                    pass
            if objects:
                return objects
        except Exception:
            pass
        raise parse_err

def call_gemini_with_fallback(prompt, chunk):
    """
    Gọi Gemini API sử dụng dòng mô hình Gemma chỉ định (Gemma 4 31B chính, Gemma 4 26B phụ)
    với khoảng cách thử lại từ 3-4s và tự động phân tích JSON cực kỳ mạnh mẽ.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise Exception("Không tìm thấy GEMINI_API_KEY.")

    genai.configure(api_key=api_key)

    # Chỉ cho phép sử dụng mô hình Gemma 4 31B hoặc Gemma 4 26B theo yêu cầu
    model_chain = ["gemma-4-31b-it", "gemma-4-26b-a4b-it"]
    last_error = None

    for model_name in model_chain:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Tránh gọi dồn dập ở lần gọi ban đầu
                time.sleep(random.uniform(0.5, 1.2))
                print(f"🤖 Đang gửi chunk ({len(chunk)} bài) qua mô hình: {model_name} (Thử lần {attempt + 1}/{max_retries})...")
                model = genai.GenerativeModel(model_name)
                
                # Không truyền response_mime_type="application/json" cho dòng Gemma để tránh lỗi 500
                response = model.generate_content(prompt)

                if not response.text:
                    raise ValueError("Nhận phản hồi rỗng từ API.")

                # Dùng bộ parse JSON siêu cấp cứu dành riêng cho Gemma
                results = robust_json_loads(response.text)
                return results, model_name

            except Exception as e:
                last_error = e
                print(f"⚠️ Thất bại khi gọi {model_name} ở lần thử {attempt + 1}: {e}")
                # Khoảng thời gian thử lại cố định từ 3s đến 4s theo yêu cầu
                sleep_time = random.uniform(3.0, 4.0)
                print(f"⏳ Đang tạm dừng {sleep_time:.2f}s trước khi thử lại...")
                time.sleep(sleep_time)

    raise Exception(f"Tất cả các mô hình Gemma trong chuỗi ({model_chain}) đều gặp lỗi. Lỗi cuối cùng: {last_error}")

def classify_chunk_with_gemini(chunk, delay=0.0):
    """Phân loại một nhóm bài viết sử dụng mô hình Gemini kèm theo rà soát địa bàn Hà Nội."""
    if delay > 0:
        time.sleep(delay)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ [LOI] Khong tim thay GEMINI_API_KEY trong bien moi truong. Bo qua phan loai cho chunk nay.")
        return []

    articles_data = []
    article_dict = {}
    for art in chunk:
        articles_data.append({
            "id": art["id"],
            "title": art["title"],
            "summary": art["summary"][:200] if art["summary"] else ""
        })
        article_dict[art["id"]] = art

    n = len(chunk)
    # Dry Command Prompt bằng tiếng Việt tối ưu cho Gemini tích hợp rà soát Hà Nội địa phương
    prompt = f"""Dưới đây là danh sách dữ liệu đầu vào chứa {n} bài viết:
{json.dumps(articles_data, ensure_ascii=False, indent=2)}

Nhiệm vụ: Phân tích kỹ nội dung của {n} bài viết. Dựa vào tư duy pháp lý, hãy xác định xem bài viết có phản ánh NGUY CƠ hoặc DẤU HIỆU vi phạm pháp luật thuộc 1 trong 12 lĩnh vực bảo vệ dân sự công ích hay không, đồng thời xác minh địa bàn xảy ra có thuộc HÀ NỘI hay không. 

Dưới đây là 12 lĩnh vực và CÁC VÍ DỤ TIÊU BIỂU (lưu ý: bạn CẦN NHẬN DIỆN CẢ NHỮNG HÀNH VI TƯƠNG TỰ KHÁC gây tổn hại đến quyền lợi hợp pháp trong từng lĩnh vực, không chỉ giới hạn ở các ví dụ này):

[NHÓM BẢO VỆ NGƯỜI YẾU THẾ]
1=Trẻ em (Ví dụ: Bạo hành, bóc lột, xâm hại, bỏ rơi, không được đến trường...)
2=Người cao tuổi (Ví dụ: Ngược đãi, lừa đảo chiếm đoạt tài sản, viện dưỡng lão sai phạm...)
3=Người khuyết tật (Ví dụ: Phân biệt đối xử, lừa đảo, hạ tầng không đảm bảo tiếp cận...)
4=Phụ nữ mang thai/nuôi con nhỏ (Ví dụ: Sa thải trái luật, vi phạm chế độ thai sản, bạo hành gia đình...)
5=Dân tộc thiểu số (Ví dụ: Lừa đảo, lợi dụng tín ngưỡng, xâm phạm đất đai/tập quán...)
6=Người mất năng lực hành vi (Ví dụ: Chiếm đoạt tài sản, giám hộ sai quy định, bạo hành tại cơ sở y tế...)

[NHÓM LỢI ÍCH CÔNG]
7=Đầu tư công (Ví dụ: Chậm tiến độ, đội vốn, đấu thầu sai quy định, thi công kém chất lượng, lãng phí...)
8=Đất đai/Tài sản công (Ví dụ: Phân lô bán nền trái phép, lấn chiếm đất công, giao đất sai thẩm quyền, bỏ hoang công sở...)
9=Môi trường (Ví dụ: Xả thải trộm, khai thác khoáng sản trái phép, xả khí thải, phá rừng...)
10=Di sản văn hóa (Ví dụ: Xâm phạm di tích, tu bổ làm hỏng di tích, trộm cắp cổ vật...)
11=An toàn thực phẩm/Dược phẩm (Ví dụ: Ngộ độc tập thể, thực phẩm bẩn, thuốc giả, cơ sở y tế không phép...)
12=Người tiêu dùng (Ví dụ: Lừa đảo qua mạng, hàng giả/nhái, rò rỉ thông tin cá nhân, quảng cáo sai sự thật, đa cấp trái phép...)

CHÚ Ý ĐẶC BIỆT QUAN TRỌNG:
- Cần chú ý đặc biệt, nhạy bén đánh giá kỹ các tin bài về KẾT LUẬN THANH TRA, KIỂM TOÁN NHÀ NƯỚC hoặc phản ánh sai phạm do cơ quan chuyên ngành chỉ ra liên quan đến Đất đai/Tài nguyên/Tài sản công (8), Đầu tư công (7), Môi trường (9) (đặc biệt tại HÀ NỘI).
- Những vụ việc có dấu hiệu lãng phí, thất thoát, lấn chiếm sử dụng trái phép tài sản công, đất công. 
Những bài này CẦN PHẢI được nhận diện nhạy bén, đánh giá kỹ để gán is_matched: true và domain_id phù hợp.

[QUY TẮC RÀ SOÁT ĐỊA PHƯƠNG (HÀ NỘI):]
- is_hanoi = true nếu vụ việc được xác nhận xảy ra tại Hà Nội.
- is_hanoi = true nếu địa danh xảy ra vụ việc KHÔNG rõ ràng, mập mờ hoặc không được nhắc tới cụ thể trong tiêu đề và tóm tắt (Mặc định giữ lại để con người thẩm duyệt).
- is_hanoi = false CHỈ KHI sự việc được khẳng định rõ ràng là xảy ra hoàn toàn ở các tỉnh thành khác (ví dụ: TP.HCM, Đà Nẵng, Hải Phòng, Quảng Ninh, Bình Dương, Đồng Nai, Khánh Hòa...) và không liên quan gì tới Hà Nội.
- CỰC KỲ CHÚ Ý các địa danh đường phố, phường, quận đặc trưng tại Hà Nội (ví dụ: đường Láng, Đê La Thành, Khâm Thiên, Bà Triệu, Tràng Tiền, Nguyễn Trãi, Đống Đa, Cầu Giấy, Hoàn Kiếm, Ba Đình, Tây Hồ, Hai Bà Trưng, Hoàng Mai, Thanh Xuân, Hà Đông, Mỹ Đình, Long Biên, v.v.). Nếu xuất hiện các từ này mà không đi kèm tên thành phố, hãy tự động nhận diện là thuộc Hà Nội và đặt is_hanoi = true.

Quy tắc chấm điểm:
- is_matched: true nếu bài viết phản ánh hành vi, sự kiện CÓ NGUY CƠ vi phạm pháp luật hoặc đang VI PHẠM thực tế thuộc 12 lĩnh vực trên. Ngược lại false.
- domain_id: Đặt từ 1 đến 12 tương ứng với lĩnh vực bị xâm phạm nếu is_matched là true. Ngược lại đặt là 0.
- match_reason: Tóm tắt lý do vi phạm cực ngắn gọn (dưới 10 từ).
- is_hanoi: Đặt true/false theo quy tắc rà soát địa phương Hà Nội nêu trên.
- hanoi_reason: Tóm tắt lý do định vị địa lý cực ngắn gọn bằng tiếng Việt (dưới 8 từ, ví dụ: 'đường Láng', 'quận Cầu Giấy', 'không rõ vị trí - giữ lại', hoặc 'Quận 1, TP.HCM').

Định dạng đầu ra: Trả về DUY NHẤT một chuỗi JSON Array chứa chính xác {n} đối tượng (TUYỆT ĐỐI không viết thêm lời giới thiệu hay giải thích nào khác):
[
  {{"article_id": <int>, "is_matched": <bool>, "domain_id": <int>, "match_reason": "<tóm tắt lý do>", "confidence_score": <điểm từ 0.0-1.0>, "is_hanoi": <bool>, "hanoi_reason": "<lý do địa lý>"}}
]"""

    try:
        results, model_used = call_gemini_with_fallback(prompt, chunk)
        for res in results:
            aid = res.get("article_id")
            if aid in article_dict:
                res["title"] = article_dict[aid].get("title", "")
                res["summary"] = article_dict[aid].get("summary", "")
                res["url"] = article_dict[aid].get("url", "")
                res["is_hanoi"] = res.get("is_hanoi", True)
                res["hanoi_reason"] = res.get("hanoi_reason", "Không rõ")
                
                is_matched = res.get("is_matched", False)
                is_hanoi = res.get("is_hanoi", True)
                if is_matched:
                    if is_hanoi:
                        res["classification_status"] = "AI_VERIFIED"
                    else:
                        res["classification_status"] = "LOCATION_REJECTED"
                else:
                    res["classification_status"] = "AI_REJECTED"
                    
                res["classifier_model"] = model_used
        return results
    except Exception as e:
        print(f"❌ [LOI] Chuoi goi API that bai hoan toan cho chunk nay: {e}. Bo qua de thu lai sau.")
        return []

# --- CHƯƠNG TRÌNH CHÍNH CHẠY PIPELINE ---
def main():
    print("🧠 BẮT ĐẦU CHẠY PIPELINE PHÂN LOẠI & SO KHỚP LAI (ML TRIAGE HYBRID CLASSIFIER) 🧠\n")
    
    # Import hàm kết nối DB
    from crawler_db import init_db, get_unclassified_articles, save_classified_article, save_classified_articles_batch
    
    # Khởi tạo hoặc nâng cấp bảng CSDL
    init_db()
    
    # 0. Tự động thu hồi các bài viết từng bị cào/phân loại offline bằng ML Fallback để AI phân loại lại chất lượng cao
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM classified_articles WHERE classifier_model = 'ML Offline Fallback'")
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        if deleted_count > 0:
            print(f"🔄 Đã tự động thu hồi {deleted_count} bài viết từng phân loại bằng ML Fallback để xếp hàng phân loại lại bằng AI...")
    except Exception as e:
        print(f"⚠️ Không thể dọn dẹp dữ liệu ML Fallback cũ: {e}")
    
    # 1. Đọc danh sách bài viết chưa được phân loại từ DB
    unclassified = get_unclassified_articles()
    total_unclassified = len(unclassified)
    print(f"📂 Tìm thấy {total_unclassified} bài viết thô chưa được xử lý so khớp.")
    
    if total_unclassified == 0:
        print("✨ Tuyệt vời! Toàn bộ bài viết trong DB đã được phân loại.")
        return

    # 2. CHUẨN BỊ DỮ LIỆU ĐẨY LÊN AI (100% AI - BỎ QUA MACHINE LEARNING THEO YÊU CẦU MỚI)
    print(f"🔍 Đang chuẩn bị {total_unclassified} bài viết mới để đẩy 100% lên AI rà soát...")
    suspect_articles = unclassified  # Đưa toàn bộ bài chưa phân loại lên AI
    
    if not suspect_articles:
        print("\n🎉 HOÀN THÀNH: Không có tin bài nào cần gửi lên AI.")
        return

    # 3. CHẠY LỚP 2 (CHỈ XỬ LÝ VÙNG VÀNG): Chia nhóm nhỏ và gửi lên Gemini
    chunk_size = 50  # Tăng lên 80 bài/Prompt để tối ưu số lần gọi API và cải thiện RPD
    chunks = [suspect_articles[i:i + chunk_size] for i in range(0, len(suspect_articles), chunk_size)]

    print(f"\n⚡ Đang gửi {len(suspect_articles)} bài Vùng Vàng lên AI thẩm định sâu (chia làm {len(chunks)} lô x {chunk_size} bài)...")

    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        primary_model = os.getenv("GEMINI_MODEL", "gemma-4-31b-it")
        print(f"🤖 CHẾ ĐỘ CHẠY: [ONLINE] Sử dụng mô hình chính {primary_model} (kèm cơ chế tự động chuyển đổi & thử lại thông minh)")
    else:
        print("🔌 CHẾ ĐỘ CHẠY: [OFFLINE FALLBACK] Không có API Key, đẩy Vùng Vàng xuống mức ML Fallback.")

    final_results = []
    
    # Quét song song các chunk sử dụng tối đa 15 luồng đồng thời theo yêu cầu
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = {}
        for idx, chk in enumerate(chunks):
            # SỬA LỖI: Không nhân delay với idx (sẽ bị cộng dồn lên hàng trăm giây). 
            # Dùng modulo 12 để rải đều 12 thread ra mỗi thread cách nhau 1.5 giây.
            delay = (idx % 12) * 1.5
            futures[executor.submit(classify_chunk_with_gemini, chk, delay)] = chk
        
        for future in as_completed(futures):
            try:
                res = future.result()
                if res:
                    final_results.extend(res)
            except Exception as e:
                print(f"❌ Lỗi xử lý luồng AI: {e}")
                
    # 4. Đối chiếu và chạy trên máy trước (Xử lý và hiển thị cục bộ)
    ai_matched_count = 0
    records_to_save = []
    
    print("\n🖥️  ĐANG ĐỐI CHIẾU VÀ PHÂN LOẠI CỤC BỘ TRÊN MÁY:")
    for res in final_results:
        raw_id = res.get("article_id")
        is_matched = res.get("is_matched", False)
        dom_id = res.get("domain_id", 0)
        reason = res.get("match_reason", "Không xác định")
        score = res.get("confidence_score", 0.0)
        title = res.get("title", "")
        summary = res.get("summary", "")
        url = res.get("url", "")
        c_status = res.get("classification_status", "UNKNOWN")
        c_model = res.get("classifier_model", os.getenv("GEMINI_MODEL", "gemma-4-31b-it"))
        
        # Nếu AI phán quyết không khớp
        if not is_matched:
            dom_id = 0
            reason = f"Xác định an toàn (Score: {score})"
        else:
            # Rà soát địa phương Hà Nội
            is_hanoi = res.get("is_hanoi", True)
            hanoi_reason = res.get("hanoi_reason", "Không rõ")
            if not is_hanoi:
                c_status = "LOCATION_REJECTED"
                reason = f"[Loại vì không thuộc HN: {hanoi_reason}] {reason}"
            else:
                reason = f"[Hà Nội: {hanoi_reason}] {reason}"
        
        # Hiển thị kết quả đối chiếu cục bộ trên máy
        if is_matched and c_status != "LOCATION_REJECTED":
            print(f"✅ [KHỚP] Lĩnh vực {dom_id} | {title[:65]}... (Độ tin cậy: {score:.2f}) | Lý do: {reason}")
        elif c_status == "LOCATION_REJECTED":
            print(f"❌ [LOẠI ĐỊA BÀN] {title[:65]}... | Lý do: {reason}")
            
        # Chuẩn bị bản ghi lưu hàng loạt
        rec = (
            raw_id,
            dom_id,
            reason,
            score,
            title,
            summary,
            url,
            c_status,
            c_model
        )
        records_to_save.append(rec)
        
        if dom_id > 0 and c_status != "LOCATION_REJECTED":
            ai_matched_count += 1
            
    # 5. Gửi kết quả lên CSDL đồng bộ bằng Batch Transaction
    if records_to_save:
        print(f"\n⚡ Đang đồng bộ gửi hàng loạt {len(records_to_save)} bài viết đã phân loại lên CSDL...")
        saved_count = save_classified_articles_batch(records_to_save)
        print(f"🎉 Đồng bộ hoàn tất! Đã cập nhật {saved_count} bài viết trong CSDL.")
            
    # Tự động loại bỏ hoàn toàn các tin LOCATION_REJECTED bằng cách set human_evaluation = 0 trực tiếp trong DB
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("UPDATE classified_articles SET human_evaluation = 0 WHERE classification_status = 'LOCATION_REJECTED' AND human_evaluation IS NULL")
        rejected_count = cursor.rowcount
        conn.commit()
        conn.close()
        if rejected_count > 0:
            print(f"🧹 Tự động loại bỏ và chuyển {rejected_count} bài viết không thuộc địa bàn Hà Nội sang tab 'Bị loại bỏ'.")
    except Exception as e:
        print(f"⚠️ Lỗi tự động loại bỏ tin ngoài địa bàn Hà Nội: {e}")
            
    print(f"\n🎉 HOÀN THÀNH PIPELINE TRIAGE:")
    print(f"   - Tổng số tin bài gửi lên AI kiểm duyệt (Vùng Vàng): {len(suspect_articles)}")
    print(f"   - Tổng số tin bài AI thẩm định vi phạm tại Hà Nội: {ai_matched_count}")
    
    # 5. Xuất báo cáo thống kê trực quan
    print("\n================ BÁO CÁO THỐNG KÊ LĨNH VỰC BẢO VỆ (NGHỊ QUYẾT 205) ================")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT domain_id, classification_status, COUNT(*) 
        FROM classified_articles 
        WHERE domain_id > 0 
        GROUP BY domain_id, classification_status
    ''')
    stats = cursor.fetchall()
    
    if stats:
        for dom_id, status, count in sorted(stats):
            name = DOMAINS.get(dom_id, {"name": "Không xác định"})["name"]
            print(f"📌 {name:<60} | [{status}] : {count:>3} bài")
    else:
        print("☘️ Chưa phát hiện tin bài vi phạm/cần bảo vệ nào.")
    print("==================================================================================\n")
    conn.close()

if __name__ == "__main__":
    main()
