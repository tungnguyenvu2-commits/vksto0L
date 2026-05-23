import sqlite3
import os
import datetime
import db_adapter  # Lớp tương thích SQLite ↔ PostgreSQL

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
        if database == DB_FILE or database == "crawler_data.db" or "crawler_data.db" in str(database):
            pg_conn = psycopg2.connect(os.getenv("DATABASE_URL"))
            return PGConnWrapper(pg_conn)
        return original_sqlite_connect(database, *args, **kwargs)
    sqlite3.connect = custom_connect

# Đường dẫn file SQLite (chỉ dùng local, bỏ qua khi có DATABASE_URL)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "crawler_data.db")

DEFAULT_SOURCES = [
    # 1. Khối Báo CAND
    ("Báo CAND - Thời sự", "Nội chính / Lực lượng vũ trang", "https://cand.com.vn/rss/Thoi-su-c1103.rss"),
    ("Báo CAND - Pháp luật", "Nội chính / Lực lượng vũ trang", "https://cand.com.vn/rss/Phap-luat-c1108.rss"),
    ("Báo CAND - Kinh tế", "Nội chính / Lực lượng vũ trang", "https://cand.com.vn/rss/Kinh-te-c1104.rss"),

    # 2. Khối Báo Giao Thông
    ("Báo Giao Thông - Thời sự", "Kinh tế / Chuyên ngành", "https://www.baogiaothong.vn/rss/thoi-su.rss"),
    ("Báo Giao Thông - Pháp luật", "Kinh tế / Chuyên ngành", "https://www.baogiaothong.vn/rss/phap-luat.rss"),

    # 3. Khối VTV News
    ("VTV News - Xã hội", "Báo đại chúng", "https://vtv.vn/rss/xa-hoi.rss"),
    ("VTV News - Pháp luật", "Báo đại chúng", "https://vtv.vn/rss/phap-luat.rss"),
    ("VTV News - Kinh tế", "Báo đại chúng", "https://vtv.vn/rss/kinh-te.rss"),

    # 4. Khối Báo Người Lao Động
    ("Báo Người Lao Động - Thời sự", "Báo đại chúng", "https://nld.com.vn/rss/thoi-su.rss"),
    ("Báo Người Lao Động - Pháp luật", "Báo đại chúng", "https://nld.com.vn/rss/phap-luat.rss"),
    ("Báo Người Lao Động - Kinh tế", "Báo đại chúng", "https://nld.com.vn/rss/kinh-te.rss"),
    ("Báo Người Lao Động - Sức khỏe", "Chuyên ngành", "https://nld.com.vn/rss/suc-khoe.rss"),

    # 5. Khối Báo VnExpress
    ("Báo VnExpress - Mới nhất", "Báo lớn", "https://vnexpress.net/rss/tin-moi-nhat.rss"),
    ("Báo VnExpress - Thời sự", "Báo lớn", "https://vnexpress.net/rss/thoi-su.rss"),
    ("Báo VnExpress - Pháp luật", "Báo lớn", "https://vnexpress.net/rss/phap-luat.rss"),
    ("Báo VnExpress - Kinh doanh", "Báo lớn", "https://vnexpress.net/rss/kinh-doanh.rss"),
    ("Báo VnExpress - Giáo dục", "Chuyên ngành", "https://vnexpress.net/rss/giao-duc.rss"),
    ("Báo VnExpress - Thế giới", "Báo lớn", "https://vnexpress.net/rss/the-gioi.rss"),

    # 6. Khối Báo Tuổi Trẻ
    ("Báo Tuổi Trẻ - Mới nhất", "Báo lớn", "https://tuoitre.vn/rss/tin-moi-nhat.rss"),
    ("Báo Tuổi Trẻ - Thời sự", "Báo lớn", "https://tuoitre.vn/rss/thoi-su.rss"),
    ("Báo Tuổi Trẻ - Pháp luật", "Báo lớn", "https://tuoitre.vn/rss/phap-luat.rss"),
    ("Báo Tuổi Trẻ - Kinh doanh", "Báo lớn", "https://tuoitre.vn/rss/kinh-doanh.rss"),
    ("Báo Tuổi Trẻ - Sức khỏe", "Báo lớn", "https://tuoitre.vn/rss/suc-khoe.rss"),
    ("Báo Tuổi Trẻ - Thế giới", "Báo lớn", "https://tuoitre.vn/rss/the-gioi.rss"),
    ("Báo Tuổi Trẻ - Giáo dục", "Chuyên ngành", "https://tuoitre.vn/rss/giao-duc.rss"),

    # 7. Khối Báo Thanh Niên
    ("Báo Thanh Niên - Mới nhất", "Báo lớn", "https://thanhnien.vn/rss/home.rss"),
    ("Báo Thanh Niên - Thời sự", "Báo lớn", "https://thanhnien.vn/rss/thoi-su.rss"),
    ("Báo Thanh Niên - Kinh tế", "Báo lớn", "https://thanhnien.vn/rss/kinh-te.rss"),
    ("Báo Thanh Niên - Sức khỏe", "Báo lớn", "https://thanhnien.vn/rss/suc-khoe.rss"),
    ("Báo Thanh Niên - Thế giới", "Báo lớn", "https://thanhnien.vn/rss/the-gioi.rss"),
    ("Báo Thanh Niên - Giáo dục", "Chuyên ngành", "https://thanhnien.vn/rss/giao-duc.rss"),

    # 8. Khối Báo VietNamNet
    ("Báo VietNamNet - Thời sự", "Báo lớn", "https://vietnamnet.vn/rss/thoi-su.rss"),
    ("Báo VietNamNet - Pháp luật", "Báo lớn", "https://vietnamnet.vn/rss/phap-luat.rss"),
    ("Báo VietNamNet - Kinh doanh", "Báo lớn", "https://vietnamnet.vn/rss/kinh-doanh.rss"),
    ("Báo VietNamNet - Thế giới", "Báo lớn", "https://vietnamnet.vn/rss/the-gioi.rss"),
    ("Báo VietNamNet - Giáo dục", "Chuyên ngành", "https://vietnamnet.vn/rss/giao-duc.rss"),

    # 9. Khối Báo Nhân Dân (Tổng hợp 36 kênh chất lượng từ nhandan.vn/rss.html)
    ("Báo Nhân Dân - Trang chủ", "Báo lớn", "https://nhandan.vn/rss/home.rss"),
    ("Báo Nhân Dân - Chính trị", "Báo lớn", "https://nhandan.vn/rss/chinhtri-1171.rss"),
    ("Báo Nhân Dân - Xã luận", "Báo lớn", "https://nhandan.vn/rss/xa-luan-1176.rss"),
    ("Báo Nhân Dân - Bình luận - Phê phán", "Báo lớn", "https://nhandan.vn/rss/binh-luan-phe-phan-1180.rss"),
    ("Báo Nhân Dân - Xây dựng Đảng", "Báo lớn", "https://nhandan.vn/rss/xay-dung-dang-1179.rss"),
    ("Báo Nhân Dân - Kinh tế", "Báo lớn", "https://nhandan.vn/rss/kinhte-1185.rss"),
    ("Báo Nhân Dân - Tài chính – Chứng khoán", "Báo lớn", "https://nhandan.vn/rss/chungkhoan-1191.rss"),
    ("Báo Nhân Dân - Thông tin hàng hóa", "Báo lớn", "https://nhandan.vn/rss/thong-tin-hang-hoa-1203.rss"),
    ("Báo Nhân Dân - Văn hóa", "Báo lớn", "https://nhandan.vn/rss/vanhoa-1251.rss"),
    ("Báo Nhân Dân - Xã hội", "Báo lớn", "https://nhandan.vn/rss/xahoi-1211.rss"),
    ("Báo Nhân Dân - BHXH và cuộc sống", "Báo lớn", "https://nhandan.vn/rss/bhxh-va-cuoc-song-1222.rss"),
    ("Báo Nhân Dân - Người tốt việc tốt", "Báo lớn", "https://nhandan.vn/rss/nguoi-tot-viec-tot-1319.rss"),
    ("Báo Nhân Dân - Pháp luật", "Báo lớn", "https://nhandan.vn/rss/phapluat-1287.rss"),
    ("Báo Nhân Dân - Du lịch", "Báo lớn", "https://nhandan.vn/rss/du-lich-1257.rss"),
    ("Báo Nhân Dân - Thế giới", "Báo lớn", "https://nhandan.vn/rss/thegioi-1231.rss"),
    ("Báo Nhân Dân - Bình luận quốc tế", "Báo lớn", "https://nhandan.vn/rss/binh-luan-quoc-te-1236.rss"),
    ("Báo Nhân Dân - ASEAN", "Báo lớn", "https://nhandan.vn/rss/asean-704471.rss"),
    ("Báo Nhân Dân - Châu Phi", "Báo lớn", "https://nhandan.vn/rss/chau-phi-704476.rss"),
    ("Báo Nhân Dân - Châu Mỹ", "Báo lớn", "https://nhandan.vn/rss/chau-my-704475.rss"),
    ("Báo Nhân Dân - Châu Âu", "Báo lớn", "https://nhandan.vn/rss/chau-au-704474.rss"),
    ("Báo Nhân Dân - Trung Đông", "Báo lớn", "https://nhandan.vn/rss/trung-dong-704473.rss"),
    ("Báo Nhân Dân - Châu Á-TBD", "Báo lớn", "https://nhandan.vn/rss/chau-a-tbd-704472.rss"),
    ("Báo Nhân Dân - Thể thao", "Báo lớn", "https://nhandan.vn/rss/thethao-1224.rss"),
    ("Báo Nhân Dân - Giáo dục", "Báo lớn", "https://nhandan.vn/rss/giaoduc-1303.rss"),
    ("Báo Nhân Dân - Y tế", "Báo lớn", "https://nhandan.vn/rss/y-te-1309.rss"),
    ("Báo Nhân Dân - Góc tư vấn", "Báo lớn", "https://nhandan.vn/rss/goc-tu-van-1311.rss"),
    ("Báo Nhân Dân - Khoa học - Công nghệ", "Báo lớn", "https://nhandan.vn/rss/khoahoc-congnghe-1292.rss"),
    ("Báo Nhân Dân - Phòng, chống tội phạm công nghệ cao", "Báo lớn", "https://nhandan.vn/rss/phong-chong-toi-pham-cong-nghe-cao-2025-704717.rss"),
    ("Báo Nhân Dân - Môi trường", "Báo lớn", "https://nhandan.vn/rss/moi-truong-1296.rss"),
    ("Báo Nhân Dân - Bạn đọc", "Báo lớn", "https://nhandan.vn/rss/bandoc-1315.rss"),
    ("Báo Nhân Dân - Đường dây nóng", "Báo lớn", "https://nhandan.vn/rss/duong-day-nong-1316.rss"),
    ("Báo Nhân Dân - Điều tra qua thư bạn đọc", "Báo lớn", "https://nhandan.vn/rss/dieu-tra-qua-thu-ban-doc-1317.rss"),
    ("Báo Nhân Dân - Kiểm chứng thông tin", "Báo lớn", "https://nhandan.vn/rss/factcheck-658978.rss"),
    ("Báo Nhân Dân - Tri thức chuyên sâu", "Báo lớn", "https://nhandan.vn/rss/tri-thuc-chuyen-sau-704477.rss"),
    ("Báo Nhân Dân - 54 dân tộc Việt Nam", "Báo lớn", "https://nhandan.vn/rss/54-dan-toc-704489.rss"),
    ("Báo Nhân Dân - Chương trình OCOP", "Báo lớn", "https://nhandan.vn/rss/ocop-704555.rss"),

    # 10. Khối Báo Sức khỏe & Đời sống
    ("Báo Sức khỏe & Đời sống - Mới nhất", "Chuyên ngành", "https://suckhoedoisong.vn/rss/home.rss"),
    ("Báo Sức khỏe & Đời sống - Thời sự y tế", "Chuyên ngành", "https://suckhoedoisong.vn/rss/thoi-su-y-te.rss"),
    ("Báo Sức khỏe & Đời sống - An toàn thực phẩm", "Chuyên ngành", "https://suckhoedoisong.vn/rss/an-toan-thuc-pham.rss"),
    ("Báo Sức khỏe & Đời sống - Dược phẩm", "Chuyên ngành", "https://suckhoedoisong.vn/rss/thuoc-va-suc-khoe.rss"),

    # 11. Khối Báo Dân Trí (Mới bổ sung)
    ("Báo Dân Trí - Mới nhất", "Báo lớn", "https://dantri.com.vn/rss/home.rss"),
    ("Báo Dân Trí - Xã hội", "Báo lớn", "https://dantri.com.vn/rss/xa-hoi.rss"),
    ("Báo Dân Trí - Pháp luật", "Chuyên ngành Pháp luật", "https://dantri.com.vn/rss/phap-luat.rss"),
    ("Báo Dân Trí - Kinh doanh", "Kinh tế / Chuyên ngành", "https://dantri.com.vn/rss/kinh-doanh.rss"),
    ("Báo Dân Trí - Sức khỏe", "Chuyên ngành", "https://dantri.com.vn/rss/suc-khoe.rss"),
    ("Báo Dân Trí - Giáo dục", "Chuyên ngành", "https://dantri.com.vn/rss/giao-duc.rss"),
    ("Báo Dân Trí - Thế giới", "Báo lớn", "https://dantri.com.vn/rss/the-gioi.rss"),

    # 12. Khối Znews (Tên miền mới znews.vn hoạt động tốt)
    ("Znews - Thời sự", "Báo lớn", "https://znews.vn/rss/thoi-su.rss"),
    ("Znews - Pháp luật", "Chuyên ngành Pháp luật", "https://znews.vn/rss/phap-luat.rss"),
    ("Znews - Kinh doanh", "Kinh tế / Chuyên ngành", "https://znews.vn/rss/kinh-doanh-tai-chinh.rss"),

    # 13. Khối Công báo điện tử Chính phủ (Mới bổ sung)
    ("Công báo điện tử Chính phủ - Công báo mới", "Công báo Chính phủ", "https://congbao.chinhphu.vn/cac-so-cong-bao-moi-dang.rss"),
    ("Công báo điện tử Chính phủ - Văn bản mới", "Công báo Chính phủ", "https://congbao.chinhphu.vn/cac-van-ban-moi-ban-hanh.rss"),

    # 14. Khối Bộ Xây dựng (Mới bổ sung)
    ("Bộ Xây dựng - Chỉ đạo điều hành", "Cổng thông tin", "http://moc.gov.vn/rss/1176/tin-chi-dao--dieu-hanh.rss"),
    ("Bộ Xây dựng - Tin hoạt động", "Cổng thông tin", "http://moc.gov.vn/rss/1173/tin-hoat-dong.rss"),
    ("Bộ Xây dựng - Giới thiệu văn bản mới", "Cổng thông tin", "http://moc.gov.vn/rss/1196/gioi-thieu-van-ban-moi.rss"),
    ("Bộ Xây dựng - Cải cách hành chính", "Cổng thông tin", "http://moc.gov.vn/rss/1166/tin-cai-cach-hanh-chinh.rss"),

    # 15. Khối Bộ Khoa học và Công nghệ (Mới bổ sung)
    ("Bộ Khoa học và Công nghệ - Trang chủ", "Cổng thông tin", "https://mst.gov.vn/rss/home.rss"),
    ("Bộ Khoa học và Công nghệ - Cẩm nang", "Cổng thông tin", "https://mst.gov.vn/rss/cam-nang-khoa-hoc-va-cong-nghe.rss"),

    # 16. Khối VnEconomy (Mới bổ sung)
    ("VnEconomy - Tài chính", "Kinh tế / Chuyên ngành", "https://vneconomy.vn/tai-chinh.rss"),
    ("VnEconomy - Tin mới", "Kinh tế / Chuyên ngành", "https://vneconomy.vn/tin-moi.rss"),

    # 17. Khối VnBusiness (Mới bổ sung)
    ("VnBusiness - Tin mới nhất", "Kinh tế / Chuyên ngành", "https://vnbusiness.vn/rss/feed.rss"),
    ("VnBusiness - Thời sự", "Kinh tế / Chuyên ngành", "https://vnbusiness.vn/rss/thoi-su.rss"),
    ("VnBusiness - Doanh nghiệp", "Kinh tế / Chuyên ngành", "https://vnbusiness.vn/rss/doanh-nghiep.rss"),

    # 18. Khối Kinh tế Môi trường (Mới bổ sung)
    ("Kinh tế Môi trường - Tin mới", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/tin-moi.rss"),
    ("Kinh tế Môi trường - Tiêu điểm", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/tieu-diem.rss"),
    ("Kinh tế Môi trường - Sự kiện", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/tieu-diem/su-kien.rss"),
    ("Kinh tế Môi trường - Bình luận", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/tieu-diem/binh-luan.rss"),
    ("Kinh tế Môi trường - Môi trường xanh", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/moi-truong-xanh.rss"),
    ("Kinh tế Môi trường - Tài nguyên", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/moi-truong-xanh/tai-nguyen.rss"),
    ("Kinh tế Môi trường - Môi trường", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/moi-truong-xanh/moi-truong.rss"),
    ("Kinh tế Môi trường - Khí hậu", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/moi-truong-xanh/khi-hau.rss"),
    ("Kinh tế Môi trường - Phòng chống thiên tai", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/moi-truong-xanh/phong-chong-thien-tai.rss"),
    ("Kinh tế Môi trường - Kinh tế xanh", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/kinh-te-xanh.rss"),
    ("Kinh tế Môi trường - Tài chính xanh", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/kinh-te-xanh/tai-chinh-xanh.rss"),
    ("Kinh tế Môi trường - Đầu tư xanh", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/kinh-te-xanh/dau-tu-xanh.rss"),
    ("Kinh tế Môi trường - Xu hướng xanh", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/kinh-te-xanh/xu-huong-xanh.rss"),
    ("Kinh tế Môi trường - Phát triển bền vững", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/phat-trien-ben-vung.rss"),
    ("Kinh tế Môi trường - Dự án môi trường", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/phat-trien-ben-vung/du-an-moi-truong.rss"),
    ("Kinh tế Môi trường - Nghiên cứu - Ứng dụng", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/phat-trien-ben-vung/nghien-cuu-ung-dung.rss"),
    ("Kinh tế Môi trường - Luật chống phá rừng", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/phat-trien-ben-vung/luat-chong-pha-rung.rss"),
    ("Kinh tế Môi trường - Thường thức Kinh tế tuần hoàn", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/phat-trien-ben-vung/thuong-thuc-kinh-te-tuan-hoan.rss"),
    ("Kinh tế Môi trường - Bất động sản xanh", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/bat-dong-san-xanh.rss"),
    ("Kinh tế Môi trường - Chính sách Môi trường", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/chinh-sach-moi-truong.rss"),
    ("Kinh tế Môi trường - Hỏi đáp chính sách", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/chinh-sach-moi-truong/hoi-dap-chinh-sach.rss"),
    ("Kinh tế Môi trường - Văn bản mới", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/chinh-sach-moi-truong/van-ban-moi.rss"),
    ("Kinh tế Môi trường - Bảo vệ môi trường", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/chinh-sach-moi-truong/bao-ve-moi-truong.rss"),
    ("Kinh tế Môi trường - Đối thoại", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/tieu-diemdoi-thoai.rss"),
    ("Kinh tế Môi trường - Việt Nam xanh", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/viet-nam-xanh.rss"),
    ("Kinh tế Môi trường - Sản phẩm xanh", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/san-pham-xanh.rss"),
    ("Kinh tế Môi trường - Các tiêu chuẩn xanh - bền vững", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/san-pham-xanh/cac-tieu-chuan-xanh-ben-vung.rss"),
    ("Kinh tế Môi trường - Tiêu dùng bền vững", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/san-pham-xanh/tieu-dung-ben-vung.rss"),
    ("Kinh tế Môi trường - KTMT và Công luận", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/ktmt-va-cong-luan.rss"),
    ("Kinh tế Môi trường - VIASEE", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/ktmt-va-cong-luan/tin-hoat-dong-viasee.rss"),
    ("Kinh tế Môi trường - Cải chính", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/ktmt-va-cong-luan/cai-chinh.rss"),
    ("Kinh tế Môi trường - Kết nối xanh", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/ket-noi-xanh.rss"),
    ("Kinh tế Môi trường - Cần biết", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/ket-noi/can-biet.rss"),
    ("Kinh tế Môi trường - Khởi nghiệp", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/ket-noi/khoi-nghiep.rss"),
    ("Kinh tế Môi trường - Môi trường Y tế - Học đường", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/ket-noi-xanh/moi-truong-y-te-hoc-duong.rss"),
    ("Kinh tế Môi trường - Thể thao vì cộng đồng", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/ket-noi/the-thao-vi-cong-dong.rss"),
    ("Kinh tế Môi trường - Doanh nghiệp tiên phong", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/ket-noi-xanh/doanh-nghiep-tien-phong.rss"),
    ("Kinh tế Môi trường - Media", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/media.rss"),
    ("Kinh tế Môi trường - Video", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/media/video.rss"),
    ("Kinh tế Môi trường - Photo", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/media/photo.rss"),
    ("Kinh tế Môi trường - Infographic", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/media/infographic.rss"),
    ("Kinh tế Môi trường - Longform", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/media/long-form.rss"),
    ("Kinh tế Môi trường - Tạp chí in", "Chuyên ngành Môi trường", "https://kinhtemoitruong.vn/rss/tap-chi-in.rss"),

    # 19. Khối Nông nghiệp Môi trường (Mới bổ sung)
    ("Báo Nông nghiệp Môi trường - Pháp luật", "Chuyên ngành Nông nghiệp", "https://nongnghiepmoitruong.vn/phap-luat.rss"),
    ("Báo Nông nghiệp Môi trường - Môi trường", "Chuyên ngành Nông nghiệp", "https://nongnghiepmoitruong.vn/moi-truong.rss"),
    ("Báo Nông nghiệp Môi trường - Chính sách", "Chuyên ngành Nông nghiệp", "https://nongnghiepmoitruong.vn/chinh-sach.rss"),
    ("Báo Nông nghiệp Môi trường - Nông thôn mới", "Chuyên ngành Nông nghiệp", "https://nongnghiepmoitruong.vn/nong-thon-moi.rss"),
    ("Báo Nông nghiệp Môi trường - Thị trường", "Chuyên ngành Nông nghiệp", "https://nongnghiepmoitruong.vn/thi-truong.rss"),
    ("Báo Nông nghiệp Môi trường - Doanh nghiệp", "Chuyên ngành Nông nghiệp", "https://nongnghiepmoitruong.vn/doanh-nghiep.rss"),
    ("Báo Nông nghiệp Môi trường - Biến đổi khí hậu", "Chuyên ngành Nông nghiệp", "https://nongnghiepmoitruong.vn/bien-doi-khi-hau.rss"),
    ("Báo Nông nghiệp Môi trường - Tài chính", "Chuyên ngành Nông nghiệp", "https://nongnghiepmoitruong.vn/tai-chinh.rss"),
    ("Báo Nông nghiệp Môi trường - OCOP", "Chuyên ngành Nông nghiệp", "https://nongnghiepmoitruong.vn/ocop.rss"),
    ("Báo Nông nghiệp Môi trường - Tri thức nông dân", "Chuyên ngành Nông nghiệp", "https://nongnghiepmoitruong.vn/tri-thuc-nong-dan.rss"),
    ("Báo Nông nghiệp Môi trường - Tri thức nghề nông", "Chuyên ngành Nông nghiệp", "https://nongnghiepmoitruong.vn/tri-thuc-nghe-nong.rss"),
    
    # 20. Bổ sung theo yêu cầu đặc biệt của người dùng
    ("Báo Thanh Niên - Blog phóng viên", "Báo lớn", "https://thanhnien.vn/rss/blog-phong-vien.rss"),
    ("Bộ Khoa học và Công nghệ", "Cổng thông tin", "https://mst.gov.vn/index.rss"),
    ("Báo Tin tức - Bạn đọc", "Bạn đọc", "https://baotintuc.vn/ban-doc.rss"),
    ("Báo Tiền Phong - Nhịp sống Thủ đô", "Nhịp sống Thủ đô", "https://tienphong.vn/rss/nhip-song-thu-do-242.rss"),
    ("Báo Tiền Phong - Môi trường", "Môi trường", "https://tienphong.vn/rss/nstd-moi-truong-313.rss"),
    ("Báo Tiền Phong - Đầu tư", "Đầu tư", "https://tienphong.vn/rss/nstd-dau-tu-245.rss"),
    ("Báo Tiền Phong - Giao thông Đô thị", "Giao thông Đô thị", "https://tienphong.vn/rss/nstd-giao-thong-do-thi-244.rss"),
    ("Báo Pháp luật TP.HCM - Ý kiến bạn đọc", "Bạn đọc", "https://plo.vn/rss/ban-doc/y-kien-ban-doc-171.rss"),
    ("Báo Pháp luật TP.HCM - Môi trường", "Môi trường", "https://plo.vn/rss/do-thi/moi-truong-179.rss"),
    
    # 21. Các kênh RSS con cụ thể của Sở GD&ĐT Hà Nội (Tin tức, Văn bản, Thông báo)
    ("Sở GD&ĐT Hà Nội - Tin tức các Phòng GD", "Cổng thông tin", "https://www.hanoi.edu.vn/rssphong.aspx?kt=tt"),
    ("Sở GD&ĐT Hà Nội - Tin tức trường Công Lập", "Cổng thông tin", "https://www.hanoi.edu.vn/rssconglap.aspx?kt=tt"),
    ("Sở GD&ĐT Hà Nội - Tin tức Khối THPT", "Cổng thông tin", "https://www.hanoi.edu.vn/rssthpt.aspx?kt=tt"),
    ("Sở GD&ĐT Hà Nội - Văn bản các Phòng GD", "Cổng thông tin", "https://www.hanoi.edu.vn/rssphong.aspx?kt=vb"),
    ("Sở GD&ĐT Hà Nội - Văn bản trường Công Lập", "Cổng thông tin", "https://www.hanoi.edu.vn/rssconglap.aspx?kt=vb"),
    ("Sở GD&ĐT Hà Nội - Văn bản Khối THPT", "Cổng thông tin", "https://www.hanoi.edu.vn/rssthpt.aspx?kt=vb"),
    ("Sở GD&ĐT Hà Nội - Thông báo các Phòng GD", "Cổng thông tin", "https://www.hanoi.edu.vn/rssphong.aspx?kt=tb"),
    ("Sở GD&ĐT Hà Nội - Thông báo trường Công Lập", "Cổng thông tin", "https://www.hanoi.edu.vn/rssconglap.aspx?kt=tb"),
    ("Sở GD&ĐT Hà Nội - Thông báo Khối THPT", "Cổng thông tin", "https://www.hanoi.edu.vn/rssthpt.aspx?kt=tb"),
    
    # 22. Các kênh RSS con cụ thể của Báo Đại Đoàn Kết (Bạn đọc, Pháp luật, Xã hội, Bất động sản, Đô thị)
    ("Báo Đại Đoàn Kết - Bạn đọc", "Bạn đọc", "https://daidoanket.vn/rss/chuyen-muc/ban-doc/feed.xml"),
    ("Báo Đại Đoàn Kết - Pháp luật", "Pháp luật", "https://daidoanket.vn/rss/chuyen-muc/phap-luat/feed.xml"),
    ("Báo Đại Đoàn Kết - Xã hội", "Xã hội", "https://daidoanket.vn/rss/chuyen-muc/xa-hoi/feed.xml"),
    ("Báo Đại Đoàn Kết - Bất động sản", "Kinh doanh", "https://daidoanket.vn/rss/chuyen-muc/bat-dong-san/feed.xml"),
    ("Báo Đại Đoàn Kết - Đô thị", "Đô thị", "https://daidoanket.vn/rss/chuyen-muc/do-thi/feed.xml"),
    
    # 23. Cổng thông tin Thanh tra Chính phủ (Chuyên mục cốt lõi của Nghị quyết 205)
    ("Thanh tra Chính phủ - Tin thanh tra", "Thanh tra", "https://thanhtra.gov.vn/rss/tin-thanh-tra.rss"),
    ("Thanh tra Chính phủ - Khiếu nại tố cáo", "Thanh tra", "https://thanhtra.gov.vn/rss/khieu-nai-to-cao.rss"),
    ("Thanh tra Chính phủ - Phòng chống tham nhũng", "Thanh tra", "https://thanhtra.gov.vn/rss/phong-chong-tham-nhung.rss"),
    
    # 24. Cổng thông tin Ủy ban Dân tộc (CEMA) & Báo Dân tộc và Tôn giáo (Nghị quyết 205 - Nhóm Dân tộc thiểu số)
    ("Ủy ban Dân tộc (CEMA) - Tin tức hoạt động", "Dân tộc", "http://www.cema.gov.vn/tin-tuc-hoat-dong.rss"),
    ("Báo Dân tộc và Tôn giáo - Trang chủ", "Dân tộc / Tôn giáo", "http://dantoctongiao.vn/index.rss"),
    ("Báo Dân tộc và Tôn giáo - Phổ biến pháp luật", "Dân tộc / Tôn giáo", "https://dantoctongiao.vn/pho-bien-phap-luat.rss"),
    ("Báo Dân tộc và Tôn giáo - Luận bàn chính sách", "Dân tộc / Tôn giáo", "https://dantoctongiao.vn/luan-ban-chinh-sach.rss"),
    ("Báo Dân tộc và Tôn giáo - Dân tộc", "Dân tộc / Tôn giáo", "https://dantoctongiao.vn/dan-toc.rss"),
    
    # 25. Các kênh RSS của Đài Phát thanh và Truyền hình Hà Nội (Hanoi Online)
    ("Hà Nội Online - An ninh trật tự", "Xã hội / Pháp luật", "https://hanoionline.vn/rss/an-ninh-trat-tu"),
    ("Hà Nội Online - Văn hóa", "Văn hóa", "https://hanoionline.vn/rss/van-hoa"),
    ("Báo Tiền Phong - Bạn đọc diễn đàn", "Bạn đọc", "https://tienphong.vn/rss/ban-doc-dien-dan-301.rss"),
    ("Báo Tiền Phong - Bạn đọc điều tra", "Bạn đọc / Điều tra", "https://tienphong.vn/rss/ban-doc-dieu-tra-300.rss"),
    
    # 26. Nguồn mới bổ sung theo yêu cầu
    ("Báo Chính phủ - Thời sự", "Báo lớn / Chính phủ", "https://baochinhphu.vn/rss/thoi-su.rss"),
    ("Báo Hà Nội Mới - Pháp luật", "Báo lớn / Pháp luật", "https://hanoimoi.vn/rss/phap-luat.rss"),
    ("Báo Pháp luật Việt Nam - Tư pháp", "Pháp luật", "https://baophapluat.vn/rss/tu-phap-268.rss")
]

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # 1. Tạo bảng chứa dữ liệu bài báo thô (có unique URL để chống trùng lặp)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS raw_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type TEXT NOT NULL,
            source_name TEXT NOT NULL,
            title TEXT,
            url TEXT UNIQUE,
            summary TEXT,
            published_date TEXT,
            crawled_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tự động nâng cấp cột từ content_snippet sang summary cho các DB cũ
    try:
        cursor.execute("ALTER TABLE raw_articles RENAME COLUMN content_snippet TO summary")
        conn.commit()
        print("🔄 Đã nâng cấp thành công cấu trúc cột: content_snippet -> summary")
    except Exception:
        conn.rollback()
    
    # 2. Tạo bảng quản lý danh sách nguồn RSS
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rss_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_name TEXT NOT NULL,
            category TEXT,
            rss_url TEXT UNIQUE NOT NULL,
            is_active INTEGER DEFAULT 1,
            last_checked TEXT,
            last_error TEXT,
            is_rss INTEGER DEFAULT 1
        )
    ''')
    
    # Tự động nâng cấp cột is_rss cho các DB cũ
    try:
        cursor.execute("ALTER TABLE rss_sources ADD COLUMN is_rss INTEGER DEFAULT 1")
        conn.commit()
        print("🔄 Đã nâng cấp thành công cấu trúc cột: is_rss vào rss_sources")
    except Exception:
        conn.rollback()
    
    # 3. Tạo bảng lưu trữ kết quả so khớp / phân loại tin bài Nghị quyết 205
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS classified_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            raw_article_id INTEGER UNIQUE NOT NULL,
            domain_id INTEGER NOT NULL,
            match_reason TEXT,
            confidence_score REAL,
            classified_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            title TEXT,
            summary TEXT,
            url TEXT,
            classification_status TEXT,
            classifier_model TEXT DEFAULT 'Không',
            FOREIGN KEY (raw_article_id) REFERENCES raw_articles (id)
        )
    ''')
    
    # Tự động nâng cấp các cột nếu DB cũ chưa có
    columns_to_add = [
        ("title", "TEXT DEFAULT NULL"),
        ("summary", "TEXT DEFAULT NULL"),
        ("url", "TEXT DEFAULT NULL"),
        ("classification_status", "TEXT DEFAULT NULL"),
        ("classifier_model", "TEXT DEFAULT 'Không'"),
        ("human_evaluation", "INTEGER DEFAULT NULL")
    ]
    for col_name, col_type in columns_to_add:
        try:
            cursor.execute(f"ALTER TABLE classified_articles ADD COLUMN {col_name} {col_type}")
            conn.commit()
            print(f"✅ Tự động thêm cột thành công: {col_name} vào classified_articles")
        except Exception:
            conn.rollback()

    # Đảm bảo các dòng cũ chưa có classifier_model sẽ được gán là 'Không'
    try:
        cursor.execute("UPDATE classified_articles SET classifier_model = 'Không' WHERE classifier_model IS NULL")
        conn.commit()
    except Exception:
        conn.rollback()
    
    # 4. Tạo bảng quản lý từ khóa Nghị quyết 205 (Cho phép sửa trực tiếp trong DB)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS resolution_keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain_id INTEGER NOT NULL,
            keyword TEXT UNIQUE NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 5. Tạo bảng vụ việc vi phạm tập trung (Chỉ chứa tin bài được xác nhận khớp)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS matched_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            raw_article_id INTEGER UNIQUE NOT NULL,
            domain_id INTEGER NOT NULL,
            source_name TEXT NOT NULL,
            title TEXT,
            summary TEXT,
            url TEXT UNIQUE,
            match_reason TEXT,
            published_date TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (raw_article_id) REFERENCES raw_articles (id)
        )
    ''')
    
    conn.commit()
    
    # Nạp 220+ từ khóa mặc định nếu bảng từ khóa trống
    cursor.execute("SELECT COUNT(*) FROM resolution_keywords")
    kw_count = cursor.fetchone()[0]
    if kw_count == 0:
        print("🌱 Đang nạp hơn 220 từ khóa pháp lý vào bảng resolution_keywords...")
        DEFAULT_KEYWORDS = [
            # Nhóm 1-6 đã có bộ từ khóa rất tốt ở ml_preprocessor.py nên ta có thể bổ sung hoặc không.
            # Ở đây ta giữ nguyên danh sách các từ khóa công ích nhưng chuyển ID về 7-12
            
            # Lĩnh vực 5: Dân tộc thiểu số (Sửa ID 1 -> 5)
            (5, "dân tộc thiểu số"), (5, "vùng đồng bào"), (5, "đồng bào thiểu số"), (5, "vùng đặc biệt khó khăn"),
            (5, "trợ giúp pháp lý"), (5, "vùng cao"), (5, "vùng sâu"), (5, "bản làng khó khăn"),
            (5, "xã biên giới"), (5, "đồng bào vùng cao"), (5, "định canh định cư"), (5, "xóa đói giảm nghèo"),
            (5, "chương trình 135"), (5, "phát triển miền núi"), (5, "đồng bào khmer"), (5, "người hmông"),
            (5, "người ba na"), (5, "người ê đê"), (5, "người dao"), (5, "vùng khó khăn"),
            
            # Lĩnh vực 7: Đầu tư công (Sửa ID 2 -> 7)
            (7, "đầu tư công"), (7, "vốn đầu tư công"), (7, "dự án oda"), (7, "vốn ngân sách"),
            (7, "giải ngân vốn công"), (7, "nguồn vốn công"), (7, "dự án nhóm a"), (7, "công trình công cộng"),
            (7, "đầu tư công trình"), (7, "ngân sách nhà nước"), (7, "kế hoạch đầu tư công"), (7, "đầu tư trung hạn"),
            (7, "chủ trương đầu tư"), (7, "giám sát đầu tư công"), (7, "thất thoát vốn đầu tư"), (7, "lãng phí vốn đầu tư"),
            (7, "nghiệm thu công trình công"), (7, "thầu dự án công"), (7, "giải ngân đầu tư"), (7, "đầu tư hạ tầng"),
            
            # Lĩnh vực 8: Tài sản công, Đất đai (Gộp cũ ID 3, 4 -> 8)
            (8, "tài sản công"), (8, "xe công"), (8, "trụ sở công"), (8, "đất công"),
            (8, "tài sản nhà nước"), (8, "công sản"), (8, "tài sản công cộng"), (8, "thất thoát tài sản nhà nước"),
            (8, "lãng phí công sản"), (8, "quản lý tài sản công"), (8, "thanh lý tài sản công"), (8, "định giá công sản"),
            (8, "sử dụng tài sản công"), (8, "thu hồi tài sản công"), (8, "thất thoát lãng phí"), (8, "mua sắm tài sản công"),
            (8, "tiêu chuẩn xe công"), (8, "trụ sở cơ quan"), (8, "nhà công vụ"), (8, "đất cơ quan"),
            (8, "quy hoạch đất công"), (8, "đất công ích"), (8, "thu hồi đất công"), (8, "tranh chấp đất công"),
            (8, "lấn chiếm đất công"), (8, "đất công cộng"), (8, "lấn chiếm vỉa hè"), (8, "quản lý đất đai"),
            (8, "quy hoạch đất"), (8, "thu hồi đất trái phép"), (8, "phát hoang đất công"), (8, "cho thuê đất công"),
            (8, "chuyển mục đích đất công"), (8, "sử dụng đất công"), (8, "đất hành lang an toàn"), (8, "đất công viên"),
            (8, "đất rừng phòng hộ"), (8, "giao đất không thu tiền"), (8, "đất dự phòng"), (8, "chế độ sử dụng đất"),
            
            # Lĩnh vực 9: Môi trường, Hệ sinh thái (Gộp cũ ID 5, 6, 7 -> 9)
            (9, "tài nguyên"), (9, "khoáng sản"), (9, "khai thác trái phép"), (9, "cát tặc"),
            (9, "quặng"), (9, "vàng tặc"), (9, "tài nguyên nước"), (9, "tài nguyên rừng"),
            (9, "vùng biển"), (9, "vùng trời"), (9, "kho số"), (9, "tần số vô tuyến"),
            (9, "quỹ đạo vệ tinh"), (9, "dữ liệu số"), (9, "tài nguyên internet"), (9, "khai thác cát lậu"),
            (9, "quặng sắt"), (9, "quặng đồng"), (9, "nước ngầm"), (9, "khai thác đá"),
            (9, "môi trường"), (9, "ô nhiễm"), (9, "xả thải"), (9, "khói bụi"),
            (9, "rác thải"), (9, "chất thải"), (9, "phát thải"), (9, "ô nhiễm nước"),
            (9, "ô nhiễm không khí"), (9, "rác thải công nghiệp"), (9, "chất thải nguy hại"), (9, "xả thải trái phép"),
            (9, "ô nhiễm dòng sông"), (9, "khí thải độc hại"), (9, "sự cố môi trường"), (9, "luật bảo vệ môi trường"),
            (9, "bụi mịn"), (9, "nước thải công nghiệp"), (9, "xử lý chất thải"), (9, "chôn lấp rác thải"),
            (9, "hệ sinh thái"), (9, "đa dạng sinh học"), (9, "rừng đặc dụng"), (9, "rừng phòng hộ"),
            (9, "động vật hoang dã"), (9, "săn bắt lậu"), (9, "săn bắn"), (9, "bảo tồn thiên nhiên"),
            (9, "vườn quốc gia"), (9, "chặt phá rừng"), (9, "phá rừng trái phép"), (9, "lâm tặc"),
            (9, "buôn bán động vật hoang dã"), (9, "sinh vật ngoại lai"), (9, "suy giảm sinh thái"), (9, "bảo tồn đa dạng"),
            (9, "khu dự trữ sinh quyển"), (9, "phá rừng đầu nguồn"), (9, "gỗ lậu"), (9, "động vật quý hiếm"),
            
            # Lĩnh vực 10: Di sản văn hóa (Sửa ID 8 -> 10)
            (10, "di sản văn hóa"), (10, "di vật"), (10, "cổ vật"), (10, "bảo vật quốc gia"),
            (10, "di tích lịch sử"), (10, "di tích quốc gia"), (10, "di sản phi vật thể"), (10, "danh lam thắng cảnh"),
            (10, "trùng tu di tích"), (10, "phá hoại di tích"), (10, "xâm hại di tích"), (10, "di sản thế giới"),
            (10, "khu di tích"), (10, "hiện vật lịch sử"), (10, "di chỉ khảo cổ"), (10, "bảo tàng lịch sử"),
            (10, "danh thắng"), (10, "tôn tạo di tích"), (10, "di sản văn hóa vật thể"), (10, "luật di sản"),
            
            # Lĩnh vực 11: An toàn thực phẩm, Dược phẩm (Gộp cũ ID 9, 10 -> 11)
            (11, "an toàn thực phẩm"), (11, "thực phẩm bẩn"), (11, "ngộ độc thực phẩm"), (11, "ngộ độc tập thể"),
            (11, "hóa chất bảo quản"), (11, "phẩm màu độc hại"), (11, "hàn the"), (11, "thu hồi thực phẩm"),
            (11, "vệ sinh an toàn"), (11, "thực phẩm không rõ nguồn gốc"), (11, "hóa chất cấm"), (11, "formol"),
            (11, "thuốc bảo vệ thực vật dư lượng"), (11, "ngộ độc bếp ăn"), (11, "thịt lợn dịch"), (11, "phụ gia độc hại"),
            (11, "ngộ độc rượu"), (11, "ngộ độc nấm"), (11, "thực phẩm ôi thiu"), (11, "vệ sinh thú y"),
            (11, "an toàn dược phẩm"), (11, "thuốc giả"), (11, "thuốc quá hạn"), (11, "dược phẩm"),
            (11, "vắc xin giả"), (11, "thuốc kém chất lượng"), (11, "tác dụng phụ nguy hại"), (11, "luật dược"),
            (11, "thu hồi thuốc"), (11, "thuốc lậu"), (11, "dược liệu giả"), (11, "thuốc không rõ nguồn gốc"),
            (11, "vắc xin kém chất lượng"), (11, "phản ứng sau tiêm"), (11, "độc tính của thuốc"), (11, "dược lâm sàng"),
            (11, "kinh doanh thuốc lậu"), (11, "quầy thuốc vi phạm"), (11, "thuốc kháng sinh lạm dụng"), (11, "dược điển"),
            
            # Lĩnh vực 12: Bảo vệ quyền lợi người tiêu dùng (Sửa ID 11 -> 12)
            (12, "quyền lợi người tiêu dùng"), (12, "bảo vệ người tiêu dùng"), (12, "hàng giả"), (12, "hàng nhái"),
            (12, "lừa đảo tiêu dùng"), (12, "đa cấp biến tướng"), (12, "lừa gạt khách hàng"), (12, "bán hàng giả"),
            (12, "gian lận thương mại"), (12, "cân thiếu"), (12, "hàng kém chất lượng"), (12, "hàng xách tay lậu"),
            (12, "quảng cáo sai sự thật"), (12, "thổi phồng công dụng"), (12, "hợp đồng mẫu lừa dối"), (12, "gian lận xuất xứ"),
            (12, "tem giả"), (12, "bảo hành gian dối"), (12, "hàng trốn thuế"), (12, "sản phẩm khuyết tật")
        ]
        
        for dom_id, keyword in DEFAULT_KEYWORDS:
            try:
                cursor.execute('''
                    INSERT OR IGNORE INTO resolution_keywords (domain_id, keyword)
                    VALUES (?, ?)
                ''', (dom_id, keyword))
            except Exception:
                conn.rollback()
        conn.commit()
        print("🌱 Đã nạp thành công hơn 220 từ khóa mặc định.")
    
    # Tự động dọn dẹp các nguồn RSS cũ của Nhân Dân và Tin Tức để tránh trùng lặp hoặc lỗi thời
    try:
        cursor.execute("DELETE FROM rss_sources WHERE (source_name LIKE 'Báo Nhân Dân%' OR rss_url = 'https://baotintuc.vn/rss.htm') AND is_rss = 1")
        conn.commit()
        print("🔄 Đã dọn dẹp các nguồn RSS cũ của Nhân Dân và Tin Tức để đồng bộ mới...")
    except Exception as e:
        conn.rollback()
        print(f"⚠️ Lỗi dọn dẹp RSS cũ: {e}")

    # Tự động nạp hoặc bổ sung các nguồn RSS mặc định (Chèn thông minh nếu chưa có)
    print("🌱 Đang kiểm tra và đồng bộ danh sách nguồn RSS chất lượng cao...")
    for name, category, url in DEFAULT_SOURCES:
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO rss_sources (source_name, category, rss_url, is_active, is_rss)
                VALUES (?, ?, ?, 1, 1)
            ''', (name, category, url))
        except Exception:
            conn.rollback()
    conn.commit()
    print("🌱 Đã đồng bộ thành công danh sách nguồn RSS.")
    
    # Tự động nạp hoặc bổ sung các nguồn cào HTML trực tiếp (Không RSS)
    DEFAULT_NON_RSS_SOURCES = [
        ("Báo Thanh tra - Hoạt động ngành", "Thanh tra", "https://thanhtra.com.vn/hoat-dong-nganh-91D9B9332", 0),
        ("Báo Thanh tra - Kết luận thanh tra", "Thanh tra", "https://thanhtra.com.vn/ket-luan-thanh-tra-E17BD7A25", 0),
        ("Báo Thanh tra - Phòng chống tham nhũng", "Thanh tra", "https://thanhtra.com.vn/phong-chong-tham-nhung-A52D004FA", 0),
        ("Báo Thanh tra - Tiếp công dân", "Thanh tra", "https://thanhtra.com.vn/tiep-cong-dan-694F0F687", 0),
        ("Báo Thanh tra - Khiếu nại tố cáo", "Thanh tra", "https://thanhtra.com.vn/khieu-nai-to-cao-AAE7E0F0E", 0),
        ("Báo Thanh tra - Nhà đất", "Thanh tra", "https://thanhtra.com.vn/nha-dat-57A4B2310", 0),
        ("Báo Thanh tra - Xử lý sau thanh tra", "Thanh tra", "https://thanhtra.com.vn/xu-ly-sau-thanh-tra-976EADF26", 0),
        ("Báo Thanh tra - Điều tra", "Thanh tra", "https://thanhtra.com.vn/dieu-tra-10061C5CA", 0),
        ("Báo Thanh tra - Hồi âm", "Thanh tra", "https://thanhtra.com.vn/hoi-am-47C70F523", 0),
        ("Báo Thanh tra - Ban chỉ đạo 236", "Thanh tra", "https://thanhtra.com.vn/ban-chi-dao-236-D2B8327E4", 0),
        ("Thanh tra Hà Nội - Kết luận thanh tra", "Thanh tra", "https://thanhtra.hanoi.gov.vn/ket-luan-thanh-tra", 0),
        ("Thanh tra Hà Nội - Tin thanh tra", "Thanh tra", "https://thanhtra.hanoi.gov.vn/tin-thanh-tra", 0),
        ("Thanh tra Hà Nội - Tin tức sự kiện", "Thanh tra", "https://thanhtra.hanoi.gov.vn/tin-tuc-su-kien", 0),
        ("Sở Tư pháp Hà Nội - Tin tức", "Cổng thông tin", "https://sotuphap.hanoi.gov.vn/tin-tuc-su-kien", 0),
        ("Sở TN&MT Hà Nội - Tin tức sự kiện", "Cổng thông tin", "http://sotnmt.hanoi.gov.vn/index.php/tin-t-c/tin-t-c-s-ki-n", 0),
        ("Sở TN&MT Hà Nội - Đất đai", "Cổng thông tin", "http://sotnmt.hanoi.gov.vn/index.php/tin-t-c/d-t-dai", 0),
        ("Sở TN&MT Hà Nội - Quy hoạch đô thị", "Cổng thông tin", "https://sonnmt.hanoi.gov.vn/index.php/tin-t-c/quy-ho-c-do-th", 0),
        ("Sở TN&MT Hà Nội - Môi trường", "Cổng thông tin", "https://sonnmt.hanoi.gov.vn/index.php/tin-t-c/moi-tru-ng", 0),
        ("Sở TN&MT Hà Nội - Đất đai (Sonnmt)", "Cổng thông tin", "https://sonnmt.hanoi.gov.vn/index.php/tin-t-c/d-t-dai", 0),
        ("Sở Tài chính Hà Nội - Tin tức", "Cổng thông tin", "https://sotaichinh.hanoi.gov.vn/tin-t-c-su-kien", 0),
        ("Sở Nội vụ Hà Nội - Thông tin đấu thầu", "Cổng thông tin", "https://sonoivu.hanoi.gov.vn/thong-tin-dau-thau", 0),
        ("Sở Xây dựng Hà Nội - Tin tức", "Cổng thông tin", "https://soxaydung.hanoi.gov.vn/vi-vn/trang/tin-tuc/785153", 0),
        ("Sở Xây dựng Hà Nội - Tin chuyên ngành", "Cổng thông tin", "https://soxaydung.hanoi.gov.vn/vi-vn/chuyen-muc/tin-so-xay-dung/785153-657895", 0),
        ("Báo Tin tức - Phóng sự điều tra", "Phóng sự / Điều tra", "https://baotintuc.vn/phong-su-dieu-tra-581ct129.htm", 0),
        ("Báo Pháp luật Việt Nam - Bạn đọc đơn thư", "Bạn đọc", "https://baophapluat.vn/chuyen-muc/ban-doc-don-thu.html", 0),
        ("Báo Kiểm toán - Phòng chống tham nhũng", "Kiểm toán / Tham nhũng", "https://baokiemtoan.vn/vi/chuyen-muc/phong-chong-tham-nhung", 0),
        ("Báo Kiểm toán - Kết quả kiểm toán", "Kiểm toán / Tham nhũng", "https://baokiemtoan.vn/vi/chuyen-muc/ket-qua-kiem-toan", 0),
        
        ("Cục An toàn thực phẩm - Cảnh báo", "An toàn thực phẩm", "https://vfa.gov.vn/tin-tuc/canh-bao-ve-an-toan-thuc-pham/", 0),
        ("Cục Quản lý Dược - Xử lý vi phạm", "Dược phẩm", "https://dav.gov.vn/thong-tin-xu-ly-vi-pham-cn5.html", 0),
        ("Báo Lao Động - Điều tra theo thư bạn đọc", "Bạn đọc / Điều tra", "https://laodong.vn/dieu-tra-theo-thu-ban-doc", 0),
        ("Báo Thanh Niên - Phóng sự điều tra", "Phóng sự / Điều tra", "https://thanhnien.vn/thoi-su/phong-su--dieu-tra.htm", 0),
        ("Báo Tuổi Trẻ - Bạn đọc phản hồi", "Bạn đọc", "https://tuoitre.vn/ban-doc/phan-hoi.htm", 0),
        ("Báo Tuổi Trẻ - Đường dây nóng", "Bạn đọc", "https://tuoitre.vn/ban-doc/duong-day-nong.htm", 0),
        ("Báo Xây Dựng - Pháp luật và Thanh tra", "Pháp luật / Thanh tra", "https://baoxaydung.vn/phap-luat/thanh-tra.htm", 0),
        ("Thanh tra Chính phủ - Kết luận thanh tra", "Thanh tra", "https://thanhtra.gov.vn/ket-luan-thanh-tra", 0),
        
        # Nguồn phi RSS (Cục/Tổng cục Quản lý thị trường - Bảo vệ người tiêu dùng)
        ("Tổng cục Quản lý thị trường - Tin tức", "Quản lý thị trường", "https://dms.gov.vn/", 0),
        ("Tổng cục Quản lý thị trường - Kiểm tra kiểm soát", "Quản lý thị trường", "https://dms.gov.vn/kiem-tra-kiem-soat", 0),
        ("Tổng cục Quản lý thị trường - QLTT địa phương", "Quản lý thị trường", "https://dms.gov.vn/quan-ly-thi-truong-dia-phuong", 0),
        ("Cục Quản lý thị trường Hà Nội - Tin tức", "Quản lý thị trường", "https://hanoi.dms.gov.vn/", 0),
        ("Cục Quản lý thị trường Hà Nội - Tin tức sự kiện", "Quản lý thị trường", "https://hanoi.dms.gov.vn/tin-t%E1%BB%A9c-s%E1%BB%B1-ki%E1%BB%87n", 0),
        ("Cục Quản lý thị trường Hà Nội - Kiểm tra kiểm soát", "Quản lý thị trường", "https://hanoi.dms.gov.vn/kiem-tra-kiem-soat", 0),
        ("Cục Quản lý thị trường Hà Nội - Hoạt động", "Quản lý thị trường", "https://hanoi.dms.gov.vn/hoat-dong", 0)
    ]
    
    # Tự động dọn dẹp các nguồn phi RSS cũ để đồng bộ danh sách mới hoàn hảo nhất
    try:
        cursor.execute("DELETE FROM rss_sources WHERE is_rss = 0")
        conn.commit()
    except Exception:
        conn.rollback()
    
    print("🌱 Đang kiểm tra và đồng bộ danh sách nguồn cào HTML trực tiếp (không RSS)...")
    for name, category, url, is_rss_val in DEFAULT_NON_RSS_SOURCES:
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO rss_sources (source_name, category, rss_url, is_active, is_rss)
                VALUES (?, ?, ?, 1, ?)
            ''', (name, category, url, is_rss_val))
        except Exception:
            conn.rollback()
    conn.commit()
    print("🌱 Đã đồng bộ thành công danh sách nguồn cào HTML trực tiếp.")
        
    conn.close()
    print(f"✅ Đã khởi tạo cơ sở dữ liệu thành công tại: {DB_FILE}")

def get_active_rss_sources():
    """Lấy toàn bộ nguồn RSS đang hoạt động (is_active = 1 và is_rss = 1)"""
    conn = db_adapter.get_conn()
    cursor = db_adapter.dict_cursor(conn)
    cursor.execute("SELECT id, source_name, category, rss_url, is_active FROM rss_sources WHERE is_active = 1 AND is_rss = 1")
    sources = db_adapter.rows_to_dicts(cursor.fetchall())
    conn.close()
    return sources

def get_active_non_rss_sources():
    """Lấy toàn bộ nguồn cào HTML trực tiếp đang hoạt động (is_active = 1 và is_rss = 0)"""
    conn = db_adapter.get_conn()
    cursor = db_adapter.dict_cursor(conn)
    cursor.execute("SELECT id, source_name, category, rss_url, is_active FROM rss_sources WHERE is_active = 1 AND is_rss = 0")
    sources = db_adapter.rows_to_dicts(cursor.fetchall())
    conn.close()
    return sources

def update_source_status(source_id, last_error=None, is_active=1):
    """Cập nhật trạng thái và nhật ký lỗi của nguồn RSS"""
    conn = db_adapter.get_conn()
    cursor = db_adapter.dict_cursor(conn)
    p = db_adapter.ph()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(f"""
        UPDATE rss_sources
        SET last_checked = {p}, last_error = {p}, is_active = {p}
        WHERE id = {p}
    """, (now, last_error, is_active, source_id))
    conn.commit()
    conn.close()

def filter_new_urls(urls):
    """Lọc ra các URL chưa tồn tại trong bảng raw_articles"""
    if not urls:
        return set()
    conn = db_adapter.get_conn()
    cursor = db_adapter.dict_cursor(conn)
    p = db_adapter.ph()
    chunk_size = 500
    existing_urls = set()
    for i in range(0, len(urls), chunk_size):
        chunk = list(urls[i:i+chunk_size])
        placeholders = ",".join([p] * len(chunk))
        cursor.execute(f"SELECT url FROM raw_articles WHERE url IN ({placeholders})", chunk)
        for row in cursor.fetchall():
            existing_urls.add(row["url"] if isinstance(row, dict) else row[0])
    conn.close()
    return set(urls) - existing_urls

def save_articles(articles):
    """Lưu danh sách bài viết vào DB bằng Bulk Insert hiệu năng cao để tránh nghẽn mạng."""
    if not articles:
        return 0
        
    conn = db_adapter.get_conn()
    cursor = db_adapter.dict_cursor(conn)
    is_pg = db_adapter.is_postgres()
    p = db_adapter.ph()
    count = 0
    
    # Chuẩn bị dữ liệu dạng danh sách các tuple
    values = []
    for article in articles:
        summary_val = article.get('summary') or article.get('content_snippet')
        values.append((
            article.get('source_type'),
            article.get('source_name'),
            article.get('title'),
            article.get('url'),
            summary_val,
            article.get('published_date')
        ))
        
    try:
        if is_pg:
            from psycopg2.extras import execute_values
            query = """
                INSERT INTO raw_articles (source_type, source_name, title, url, summary, published_date)
                VALUES %s
                ON CONFLICT DO NOTHING
            """
            execute_values(cursor, query, values)
        else:
            query = f"""
                INSERT OR IGNORE INTO raw_articles (source_type, source_name, title, url, summary, published_date)
                VALUES ({p},{p},{p},{p},{p},{p})
            """
            cursor.executemany(query, values)
        conn.commit()
        count = len(articles)
    except Exception as e:
        # Fallback về từng dòng nếu có lỗi xảy ra để đảm bảo an toàn tuyệt đối
        try:
            for article in articles:
                try:
                    summary_val = article.get('summary') or article.get('content_snippet')
                    if is_pg:
                        cursor.execute(f"""
                            INSERT INTO raw_articles (source_type, source_name, title, url, summary, published_date)
                            VALUES ({p},{p},{p},{p},{p},{p})
                            ON CONFLICT DO NOTHING
                        """, (article.get('source_type'), article.get('source_name'),
                               article.get('title'), article.get('url'),
                               summary_val, article.get('published_date')))
                    else:
                        cursor.execute(f"""
                            INSERT OR IGNORE INTO raw_articles (source_type, source_name, title, url, summary, published_date)
                            VALUES ({p},{p},{p},{p},{p},{p})
                        """, (article.get('source_type'), article.get('source_name'),
                               article.get('title'), article.get('url'),
                               summary_val, article.get('published_date')))
                    count += 1
                except Exception:
                    pass
            conn.commit()
        except Exception:
            pass
    finally:
        conn.close()
        
    return count

def get_unclassified_articles():
    """Lấy toàn bộ bài viết thô chưa được phân loại"""
    conn = db_adapter.get_conn()
    cursor = db_adapter.dict_cursor(conn)
    cursor.execute('''
        SELECT id, source_type, source_name, title, url, summary, published_date
        FROM raw_articles
        WHERE id NOT IN (SELECT raw_article_id FROM classified_articles)
    ''')
    rows = db_adapter.rows_to_dicts(cursor.fetchall())
    conn.close()
    return rows

def save_classified_article(raw_article_id, domain_id, match_reason, confidence_score, title="", summary="", url="", classification_status="", classifier_model="Không"):
    """Lưu kết quả phân loại bài viết"""
    conn = db_adapter.get_conn()
    cursor = db_adapter.dict_cursor(conn)
    p = db_adapter.ph()
    is_pg = db_adapter.is_postgres()
    success = False
    try:
        if is_pg:
            cursor.execute(f"""
                INSERT INTO classified_articles
                (raw_article_id, domain_id, match_reason, confidence_score, title, summary, url, classification_status, classifier_model)
                VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p})
                ON CONFLICT DO NOTHING
            """, (raw_article_id, domain_id, match_reason, confidence_score, title, summary, url, classification_status, classifier_model))
        else:
            cursor.execute(f"""
                INSERT OR IGNORE INTO classified_articles
                (raw_article_id, domain_id, match_reason, confidence_score, title, summary, url, classification_status, classifier_model)
                VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p})
            """, (raw_article_id, domain_id, match_reason, confidence_score, title, summary, url, classification_status, classifier_model))
        conn.commit()
        success = True
    except Exception:
        pass
    conn.close()
    return success

def save_classified_articles_batch(records):
    """Lưu hàng loạt kết quả phân loại bằng Batch Transaction."""
    if not records:
        return 0
    conn = db_adapter.get_conn()
    cursor = db_adapter.dict_cursor(conn)
    p = db_adapter.ph()
    is_pg = db_adapter.is_postgres()
    count = 0
    try:
        if is_pg:
            for rec in records:
                try:
                    cursor.execute(f"""
                        INSERT INTO classified_articles
                        (raw_article_id, domain_id, match_reason, confidence_score, title, summary, url, classification_status, classifier_model)
                        VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p})
                        ON CONFLICT DO NOTHING
                    """, rec)
                    count += 1
                except Exception:
                    pass
        else:
            cursor.execute("BEGIN TRANSACTION")
            cursor.executemany(f"""
                INSERT OR IGNORE INTO classified_articles
                (raw_article_id, domain_id, match_reason, confidence_score, title, summary, url, classification_status, classifier_model)
                VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p})
            """, records)
            count = cursor.rowcount
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"⚠️ Lỗi lưu batch: {e}")
    finally:
        conn.close()
    return count

def get_keywords_from_db():
    """Lấy toàn bộ từ khóa phân loại theo từng lĩnh vực từ CSDL"""
    conn = db_adapter.get_conn()
    cursor = db_adapter.dict_cursor(conn)
    cursor.execute("SELECT domain_id, keyword FROM resolution_keywords")
    rows = cursor.fetchall()
    conn.close()
    import re
    keywords_dict = {}
    for row in rows:
        dom_id = row["domain_id"] if isinstance(row, dict) else row[0]
        keyword = row["keyword"] if isinstance(row, dict) else row[1]
        if dom_id not in keywords_dict:
            keywords_dict[dom_id] = []
        keywords_dict[dom_id].append(re.escape(keyword.lower()))
    return keywords_dict

def save_matched_case(raw_article_id, domain_id, source_name, title, summary, url, match_reason, published_date):
    """Lưu vụ việc vi phạm khớp vào bảng matched_cases"""
    conn = db_adapter.get_conn()
    cursor = db_adapter.dict_cursor(conn)
    p = db_adapter.ph()
    is_pg = db_adapter.is_postgres()
    success = False
    try:
        if is_pg:
            cursor.execute(f"""
                INSERT INTO matched_cases (raw_article_id, domain_id, source_name, title, summary, url, match_reason, published_date)
                VALUES ({p},{p},{p},{p},{p},{p},{p},{p})
                ON CONFLICT (raw_article_id) DO UPDATE SET match_reason=EXCLUDED.match_reason
            """, (raw_article_id, domain_id, source_name, title, summary, url, match_reason, published_date))
        else:
            cursor.execute(f"""
                INSERT OR REPLACE INTO matched_cases (raw_article_id, domain_id, source_name, title, summary, url, match_reason, published_date)
                VALUES ({p},{p},{p},{p},{p},{p},{p},{p})
            """, (raw_article_id, domain_id, source_name, title, summary, url, match_reason, published_date))
        conn.commit()
        success = True
    except Exception:
        pass
    conn.close()
    return success

if __name__ == "__main__":
    init_db()
