# -*- coding: utf-8 -*-
"""
crawler_db_github.py — Lớp cơ sở dữ liệu VKS BOT cho GITHUB ACTIONS
=============================================================================
Kế thừa toàn bộ logic nghiệp vụ cốt lõi từ crawler_db.py.
Tương tác trực tiếp với db_adapter_github.py và chỉ sử dụng PostgreSQL.
=============================================================================
"""

import os
import sys
import datetime
import db_adapter_github

# Đọc danh sách các nguồn RSS mặc định
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

    # 9. Khối Báo Nhân Dân
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

    # 11. Khối Báo Dân Trí
    ("Báo Dân Trí - Mới nhất", "Báo lớn", "https://dantri.com.vn/rss/home.rss"),
    ("Báo Dân Trí - Xã hội", "Báo lớn", "https://dantri.com.vn/rss/xa-hoi.rss"),
    ("Báo Dân Trí - Pháp luật", "Chuyên ngành Pháp luật", "https://dantri.com.vn/rss/phap-luat.rss"),
    ("Báo Dân Trí - Kinh doanh", "Kinh tế / Chuyên ngành", "https://dantri.com.vn/rss/kinh-doanh.rss"),
    ("Báo Dân Trí - Sức khỏe", "Chuyên ngành", "https://dantri.com.vn/rss/suc-khoe.rss"),
    ("Báo Dân Trí - Giáo dục", "Chuyên ngành", "https://dantri.com.vn/rss/giao-duc.rss"),
    ("Báo Dân Trí - Thế giới", "Báo lớn", "https://dantri.com.vn/rss/the-gioi.rss"),

    # 12. Khối Znews
    ("Znews - Thời sự", "Báo lớn", "https://znews.vn/rss/thoi-su.rss"),
    ("Znews - Pháp luật", "Chuyên ngành Pháp luật", "https://znews.vn/rss/phap-luat.rss"),
    ("Znews - Kinh doanh", "Kinh tế / Chuyên ngành", "https://znews.vn/rss/kinh-doanh-tai-chinh.rss"),

    # 13. Khối Công báo điện tử Chính phủ
    ("Công báo điện tử Chính phủ - Công báo mới", "Công báo Chính phủ", "https://congbao.chinhphu.vn/cac-so-cong-bao-moi-dang.rss"),
    ("Công báo điện tử Chính phủ - Văn bản mới", "Công báo Chính phủ", "https://congbao.chinhphu.vn/cac-van-ban-moi-ban-hanh.rss"),

    # 14. Khối Bộ Xây dựng
    ("Bộ Xây dựng - Chỉ đạo điều hành", "Cổng thông tin", "http://moc.gov.vn/rss/1176/tin-chi-dao--dieu-hanh.rss"),
    ("Bộ Xây dựng - Tin hoạt động", "Cổng thông tin", "http://moc.gov.vn/rss/1173/tin-hoat-dong.rss"),
    ("Bộ Xây dựng - Giới thiệu văn bản mới", "Cổng thông tin", "http://moc.gov.vn/rss/1196/gioi-thieu-van-ban-moi.rss"),
    ("Bộ Xây dựng - Cải cách hành chính", "Cổng thông tin", "http://moc.gov.vn/rss/1166/tin-cai-cach-hanh-chinh.rss"),

    # 15. Khối Bộ Khoa học và Công nghệ
    ("Bộ Khoa học và Công nghệ - Trang chủ", "Cổng thông tin", "https://mst.gov.vn/rss/home.rss"),
    ("Bộ Khoa học và Công nghệ - Cẩm nang", "Cổng thông tin", "https://mst.gov.vn/rss/cam-nang-khoa-hoc-va-cong-nghe.rss"),

    # 16. Khối VnEconomy
    ("VnEconomy - Tài chính", "Kinh tế / Chuyên ngành", "https://vneconomy.vn/tai-chinh.rss"),
    ("VnEconomy - Tin mới", "Kinh tế / Chuyên ngành", "https://vneconomy.vn/tin-moi.rss"),

    # 17. Khối VnBusiness
    ("VnBusiness - Tin mới nhất", "Kinh tế / Chuyên ngành", "https://vnbusiness.vn/rss/feed.rss"),
    ("VnBusiness - Thời sự", "Kinh tế / Chuyên ngành", "https://vnbusiness.vn/rss/thoi-su.rss"),
    ("VnBusiness - Doanh nghiệp", "Kinh tế / Chuyên ngành", "https://vnbusiness.vn/rss/doanh-nghiep.rss"),

    # 18. Khối Kinh tế Môi trường
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

    # 19. Khối Nông nghiệp Môi trường
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
    
    # 20. Bổ sung đặc biệt
    ("Báo Thanh Niên - Blog phóng viên", "Báo lớn", "https://thanhnien.vn/rss/blog-phong-vien.rss"),
    ("Bộ Khoa học và Công nghệ", "Cổng thông tin", "https://mst.gov.vn/index.rss"),
    ("Báo Tin tức - Bạn đọc", "Bạn đọc", "https://baotintuc.vn/ban-doc.rss"),
    ("Báo Tiền Phong - Nhịp sống Thủ đô", "Nhịp sống Thủ đô", "https://tienphong.vn/rss/nhip-song-thu-do-242.rss"),
    ("Báo Tiền Phong - Môi trường", "Môi trường", "https://tienphong.vn/rss/nstd-moi-truong-313.rss"),
    ("Báo Tiền Phong - Đầu tư", "Đầu tư", "https://tienphong.vn/rss/nstd-dau-tu-245.rss"),
    ("Báo Tiền Phong - Giao thông Đô thị", "Giao thông Đô thị", "https://tienphong.vn/rss/nstd-giao-thong-do-thi-244.rss"),
    ("Báo Pháp luật TP.HCM - Ý kiến bạn đọc", "Bạn đọc", "https://plo.vn/rss/ban-doc/y-kien-ban-doc-171.rss"),
    ("Báo Pháp luật TP.HCM - Môi trường", "Môi trường", "https://plo.vn/rss/do-thi/moi-truong-179.rss"),
    
    # 21. Cổng Sở GD&ĐT Hà Nội
    ("Sở GD&ĐT Hà Nội - Tin tức các Phòng GD", "Cổng thông tin", "https://www.hanoi.edu.vn/rssphong.aspx?kt=tt"),
    ("Sở GD&ĐT Hà Nội - Tin tức trường Công Lập", "Cổng thông tin", "https://www.hanoi.edu.vn/rssconglap.aspx?kt=tt"),
    ("Sở GD&ĐT Hà Nội - Tin tức Khối THPT", "Cổng thông tin", "https://www.hanoi.edu.vn/rssthpt.aspx?kt=tt"),
    ("Sở GD&ĐT Hà Nội - Văn bản các Phòng GD", "Cổng thông tin", "https://www.hanoi.edu.vn/rssphong.aspx?kt=vb"),
    ("Sở GD&ĐT Hà Nội - Văn bản trường Công Lập", "Cổng thông tin", "https://www.hanoi.edu.vn/rssconglap.aspx?kt=vb"),
    ("Sở GD&ĐT Hà Nội - Văn bản Khối THPT", "Cổng thông tin", "https://www.hanoi.edu.vn/rssthpt.aspx?kt=vb"),
    ("Sở GD&ĐT Hà Nội - Thông báo các Phòng GD", "Cổng thông tin", "https://www.hanoi.edu.vn/rssphong.aspx?kt=tb"),
    ("Sở GD&ĐT Hà Nội - Thông báo trường Công Lập", "Cổng thông tin", "https://www.hanoi.edu.vn/rssconglap.aspx?kt=tb"),
    ("Sở GD&ĐT Hà Nội - Thông báo Khối THPT", "Cổng thông tin", "https://www.hanoi.edu.vn/rssthpt.aspx?kt=tb"),
    
    # 22. Báo Đại Đoàn Kết
    ("Báo Đại Đoàn Kết - Bạn đọc", "Bạn đọc", "https://daidoanket.vn/rss/chuyen-muc/ban-doc/feed.xml"),
    ("Báo Đại Đoàn Kết - Pháp luật", "Pháp luật", "https://daidoanket.vn/rss/chuyen-muc/phap-luat/feed.xml"),
    ("Báo Đại Đoàn Kết - Xã hội", "Xã hội", "https://daidoanket.vn/rss/chuyen-muc/xa-hoi/feed.xml"),
    ("Báo Đại Đoàn Kết - Bất động sản", "Kinh doanh", "https://daidoanket.vn/rss/chuyen-muc/bat-dong-san/feed.xml"),
    ("Báo Đại Đoàn Kết - Đô thị", "Đô thị", "https://daidoanket.vn/rss/chuyen-muc/do-thi/feed.xml"),
    
    # 23. Thanh tra Chính phủ
    ("Thanh tra Chính phủ - Tin thanh tra", "Thanh tra", "https://thanhtra.gov.vn/rss/tin-thanh-tra.rss"),
    ("Thanh tra Chính phủ - Khiếu nại tố cáo", "Thanh tra", "https://thanhtra.gov.vn/rss/khieu-nai-to-cao.rss"),
    ("Thanh tra Chính phủ - Phòng chống tham nhũng", "Thanh tra", "https://thanhtra.gov.vn/rss/phong-chong-tham-nhung.rss"),
    
    # 24. CEMA
    ("Ủy ban Dân tộc (CEMA) - Tin tức hoạt động", "Dân tộc", "http://www.cema.gov.vn/tin-tuc-hoat-dong.rss"),
    ("Báo Dân tộc và Tôn giáo - Trang chủ", "Dân tộc / Tôn giáo", "http://dantoctongiao.vn/index.rss"),
    ("Báo Dân tộc và Tôn giáo - Phổ biến pháp luật", "Dân tộc / Tôn giáo", "https://dantoctongiao.vn/pho-bien-phap-luat.rss"),
    ("Báo Dân tộc và Tôn giáo - Luận bàn chính sách", "Dân tộc / Tôn giáo", "https://dantoctongiao.vn/luan-ban-chinh-sach.rss"),
    ("Báo Dân tộc và Tôn giáo - Dân tộc", "Dân tộc / Tôn giáo", "https://dantoctongiao.vn/dan-toc.rss"),
    
    # 25. Hanoi Online
    ("Hà Nội Online - An ninh trật tự", "Xã hội / Pháp luật", "https://hanoionline.vn/rss/an-ninh-trat-tu"),
    ("Hà Nội Online - Văn hóa", "Văn hóa", "https://hanoionline.vn/rss/van-hoa"),
    ("Báo Tiền Phong - Bạn đọc diễn đàn", "Bạn đọc", "https://tienphong.vn/rss/ban-doc-dien-dan-301.rss"),
    ("Báo Tiền Phong - Bạn đọc điều tra", "Bạn đọc / Điều tra", "https://tienphong.vn/rss/ban-doc-dieu-tra-300.rss"),
    
    # 26. Nguồn mới bổ sung
    ("Báo Chính phủ - Thời sự", "Báo lớn / Chính phủ", "https://baochinhphu.vn/rss/thoi-su.rss"),
    ("Báo Hà Nội Mới - Pháp luật", "Báo lớn / Pháp luật", "https://hanoimoi.vn/rss/phap-luat.rss"),
    ("Báo Pháp luật Việt Nam - Tư pháp", "Pháp luật", "https://baophapluat.vn/rss/tu-phap-268.rss"),

    # 27. Báo Bảo vệ pháp luật (BVPL)
    ("Báo BVPL - Giới thiệu", "Báo chí công ích", "https://baovephapluat.vn/so-do-website/rss/10"),
    ("Báo BVPL - Thời sự", "Thời sự", "https://baovephapluat.vn/so-do-website/rss/11"),
    ("Báo BVPL - Kiểm sát 24h", "Kiểm sát / Nội chính", "https://baovephapluat.vn/so-do-website/rss/12"),
    ("Báo BVPL - Vấn đề - Sự kiện", "Kiểm sát / Nội chính", "https://baovephapluat.vn/so-do-website/rss/22"),
    ("Báo BVPL - Bản tin kiểm sát", "Kiểm sát / Nội chính", "https://baovephapluat.vn/so-do-website/rss/23"),
    ("Báo BVPL - Nhân sự mới", "Kiểm sát / Nội chính", "https://baovephapluat.vn/so-do-website/rss/25"),
    ("Báo BVPL - Chính sách mới", "Kiểm sát / Nội chính", "https://baovephapluat.vn/so-do-website/rss/24"),
    ("Báo BVPL - Công tố - Kiểm sát tư pháp", "Công tố / Kiểm sát tư pháp", "https://baovephapluat.vn/so-do-website/rss/13"),
    ("Báo BVPL - Theo dòng", "Công tố / Kiểm sát tư pháp", "https://baovephapluat.vn/so-do-website/rss/26"),
    ("Báo BVPL - Khởi tố", "Công tố / Kiểm sát tư pháp", "https://baovephapluat.vn/so-do-website/rss/28"),
    ("Báo BVPL - Truy tố", "Công tố / Kiểm sát tư pháp", "https://baovephapluat.vn/so-do-website/rss/29"),
    ("Báo BVPL - An ninh trật tự", "Công tố / Kiểm sát tư pháp", "https://baovephapluat.vn/so-do-website/rss/27"),
    ("Báo BVPL - Pháp đình", "Pháp đình", "https://baovephapluat.vn/so-do-website/rss/14"),
    ("Báo BVPL - Tòa tuyên án", "Pháp đình", "https://baovephapluat.vn/so-do-website/rss/30"),
    ("Báo BVPL - Kỳ án", "Pháp đình", "https://baovephapluat.vn/so-do-website/rss/31"),
    ("Báo BVPL - Câu chuyện pháp luật", "Pháp đình", "https://baovephapluat.vn/so-do-website/rss/32"),
    ("Báo BVPL - Cải cách tư pháp", "Cải cách tư pháp", "https://baovephapluat.vn/so-do-website/rss/15"),
    ("Báo BVPL - Diễn đàn", "Cải cách tư pháp", "https://baovephapluat.vn/so-do-website/rss/33"),
    ("Báo BVPL - Thực tiễn - Kinh nghiệm", "Cải cách tư pháp", "https://baovephapluat.vn/so-do-website/rss/34"),
    ("Báo BVPL - Nhân tố điển hình", "Cải cách tư pháp", "https://baovephapluat.vn/so-do-website/rss/35"),
    ("Báo BVPL - Kinh tế", "Kinh tế", "https://baovephapluat.vn/so-do-website/rss/16"),
    ("Báo BVPL - Kinh doanh - Pháp luật", "Kinh tế", "https://baovephapluat.vn/so-do-website/rss/47"),
    ("Báo BVPL - Tài chính - Ngân hàng", "Kinh tế", "https://baovephapluat.vn/so-do-website/rss/50"),
    ("Báo BVPL - Dùng hàng Việt", "Kinh tế", "https://baovephapluat.vn/so-do-website/rss/51"),
    ("Báo BVPL - Văn hóa - Xã hội", "Văn hóa / Xã hội", "https://baovephapluat.vn/so-do-website/rss/17"),
    ("Báo BVPL - Giáo dục", "Văn hóa / Xã hội", "https://baovephapluat.vn/so-do-website/rss/38"),
    ("Báo BVPL - Y tế", "Văn hóa / Xã hội", "https://baovephapluat.vn/so-do-website/rss/39"),
    ("Báo BVPL - Đời sống xã hội", "Văn hóa / Xã hội", "https://baovephapluat.vn/so-do-website/rss/64"),
    ("Báo BVPL - Văn hóa", "Văn hóa / Xã hội", "https://baovephapluat.vn/so-do-website/rss/42"),
    ("Báo BVPL - Quốc tế", "Quốc tế", "https://baovephapluat.vn/so-do-website/rss/18"),
    ("Báo BVPL - Tin tức quốc tế", "Quốc tế", "https://baovephapluat.vn/so-do-website/rss/52"),
    ("Báo BVPL - Pháp luật 5 châu", "Quốc tế", "https://baovephapluat.vn/so-do-website/rss/53"),
    ("Báo BVPL - Chuyện lạ bốn phương", "Quốc tế", "https://baovephapluat.vn/so-do-website/rss/54"),
    ("Báo BVPL - Pháp luật - Bạn đọc", "Bạn đọc", "https://baovephapluat.vn/so-do-website/rss/19"),
    ("Báo BVPL - Tin đường dây nóng", "Bạn đọc", "https://baovephapluat.vn/so-do-website/rss/43"),
    ("Báo BVPL - Hồi âm", "Bạn đọc", "https://baovephapluat.vn/so-do-website/rss/45"),
    ("Báo BVPL - Báo chí công dân", "Bạn đọc", "https://baovephapluat.vn/so-do-website/rss/46"),
    ("Báo BVPL - Kỷ niệm 50 năm Giải phóng miền Nam", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/106"),
    ("Báo BVPL - Chào mừng Đại hội XIV của Đảng", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/113"),
    ("Báo BVPL - Bầu cử ĐBQH và HĐND 2026-2031", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/114"),
    ("Báo BVPL - Chuyển đổi xanh, tiết kiệm năng lượng", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/116"),
    ("Báo BVPL - Kỳ họp thứ nhất Quốc hội khóa XVI", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/117"),
    ("Báo BVPL - Quyết tâm thực hiện Nghị quyết Đại hội XIV", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/115"),
    ("Báo BVPL - Điều tra theo đơn thư", "Bạn đọc / Điều tra", "https://baovephapluat.vn/so-do-website/rss/44"),
    ("Báo BVPL - Kiểm sát khiếu tố", "Kiểm sát / Nội chính", "https://baovephapluat.vn/so-do-website/rss/63"),
    ("Báo BVPL - Chống tham nhũng, lãng phí", "Kiểm sát / Nội chính", "https://baovephapluat.vn/so-do-website/rss/62"),
    ("Báo BVPL - Thông tin doanh nhân - doanh nghiệp", "Kinh tế", "https://baovephapluat.vn/so-do-website/rss/61"),
    ("Báo BVPL - Tư vấn pháp luật", "Tư vấn pháp luật", "https://baovephapluat.vn/so-do-website/rss/21"),
    ("Báo BVPL - Luật sư của bạn", "Tư vấn pháp luật", "https://baovephapluat.vn/so-do-website/rss/36"),
    ("Báo BVPL - Giải đáp pháp luật", "Tư vấn pháp luật", "https://baovephapluat.vn/so-do-website/rss/37"),
    ("Báo BVPL - Giao thông", "Kinh tế", "https://baovephapluat.vn/so-do-website/rss/49"),
    ("Báo BVPL - Kỷ niệm 65 năm thành lập VKSND", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/102"),
    ("Báo BVPL - Hội thao ngành Kiểm sát XIV - 2025", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/103"),
    ("Báo BVPL - Viện trưởng VKSNDTC Nguyễn Huy Tiến", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/110"),
    ("Báo BVPL - VKSND bảo vệ người yếu thế, lợi ích công", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/112"),
    ("Báo BVPL - Đô thị - Xây dựng", "Kinh tế", "https://baovephapluat.vn/so-do-website/rss/48"),
    ("Báo BVPL - Lao động - Tiền lương", "Văn hóa / Xã hội", "https://baovephapluat.vn/so-do-website/rss/40"),
    ("Báo BVPL - Thể thao - Giải trí", "Thể thao / Giải trí", "https://baovephapluat.vn/so-do-website/rss/20"),
    ("Báo BVPL - Thể thao", "Thể thao / Giải trí", "https://baovephapluat.vn/so-do-website/rss/55"),
    ("Báo BVPL - Thương hiệu du lịch", "Thể thao / Giải trí", "https://baovephapluat.vn/so-do-website/rss/57"),
    ("Báo BVPL - Người của công chúng", "Thể thao / Giải trí", "https://baovephapluat.vn/so-do-website/rss/58"),
    ("Báo BVPL - Thời trang - Mua sắm", "Thể thao / Giải trí", "https://baovephapluat.vn/so-do-website/rss/59"),
    ("Báo BVPL - Ẩm thực", "Thể thao / Giải trí", "https://baovephapluat.vn/so-do-website/rss/60"),
    ("Báo BVPL - Vòng tay nhân ái", "Văn hóa / Xã hội", "https://baovephapluat.vn/so-do-website/rss/41"),
    ("Báo BVPL - Xây dựng, chỉnh đốn Đảng", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/65"),
    ("Báo BVPL - 5 năm thực hiện QĐ 596", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/101"),
    ("Báo BVPL - Phòng, chống dịch Covid-19", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/71"),
    ("Báo BVPL - Kỳ án Hồ Duy Hải", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/74"),
    ("Báo BVPL - Tìm hiểu truyền thống 60 năm VKSND", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/72"),
    ("Báo BVPL - Chúng tôi là kiểm sát viên", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/68"),
    ("Báo BVPL - Kỷ niệm 60 năm thành lập ngành KS", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/70"),
    ("Báo BVPL - Cúp Báo Bảo vệ pháp luật", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/69"),
    ("Báo BVPL - Nét đẹp cán bộ ngành Kiểm sát", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/76"),
    ("Báo BVPL - Góp ý dự thảo Văn kiện Đại hội XIII", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/77"),
    ("Báo BVPL - Chào mừng Đại hội Đảng bộ VKSNDTC 2025-2030", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/107"),
    ("Báo BVPL - Đưa nghị quyết của Đảng vào cuộc sống", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/78"),
    ("Báo BVPL - Phòng, chống tội phạm xâm hại trẻ em", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/79"),
    ("Báo BVPL - Phòng, chống tội phạm ma túy", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/80"),
    ("Báo BVPL - Áo dài nữ công đoàn VKSNDTC", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/81"),
    ("Báo BVPL - Quốc hội, Chính phủ với nhân dân", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/82"),
    ("Báo BVPL - Tuyên truyền Nghị quyết 84/NQ-CP", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/83"),
    ("Báo BVPL - VKS kháng nghị - kiến nghị", "Kiểm sát / Nội chính", "https://baovephapluat.vn/so-do-website/rss/84"),
    ("Báo BVPL - Longform", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/90"),
    ("Báo BVPL - Cúp Báo BVPL lần thứ XI", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/91"),
    ("Báo BVPL - Người tốt, việc tốt", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/92"),
    ("Báo BVPL - Hội thao VKSND lần thứ XII - 2023", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/95"),
    ("Báo BVPL - 20 năm xây dựng và phát triển", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/93"),
    ("Báo BVPL - Báo chí PC tham nhũng, tiêu cực", "Kiểm sát / Nội chính", "https://baovephapluat.vn/so-do-website/rss/94"),
    ("Báo BVPL - HN Viện trưởng VKS ASEAN-TQ lần 13", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/96"),
    ("Báo BVPL - Học và làm theo Bác", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/97"),
    ("Báo BVPL - Hội thao VKSND lần thứ XIII - 2024", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/98"),
    ("Báo BVPL - Báo cáo án bằng sơ đồ tư duy", "Kiểm sát / Nội chính", "https://baovephapluat.vn/so-do-website/rss/99"),
    ("Báo BVPL - Chuyển đổi số ngành KSND", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/100"),
    ("Báo BVPL - 80 năm hành trình Độc lập-Tự do-Hạnh phúc", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/109"),
    ("Báo BVPL - Giải Pickleball BVPL mở rộng I - 2025", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/111"),
    ("Báo BVPL - Hội thao VKSND lần thứ XIV - 2026", "Chuyên đề / Sự kiện", "https://baovephapluat.vn/so-do-website/rss/118")
]

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
    ("Tổng cục Quản lý thị trường - Tin tức", "Quản lý thị trường", "https://dms.gov.vn/", 0),
    ("Tổng cục Quản lý thị trường - Kiểm tra kiểm soát", "Quản lý thị trường", "https://dms.gov.vn/kiem-tra-kiem-soat", 0),
    ("Tổng cục Quản lý thị trường - QLTT địa phương", "Quản lý thị trường", "https://dms.gov.vn/quan-ly-thi-truong-dia-phuong", 0),
    ("Cục Quản lý thị trường Hà Nội - Tin tức", "Quản lý thị trường", "https://hanoi.dms.gov.vn/", 0),
    ("Cục Quản lý thị trường Hà Nội - Tin tức sự kiện", "Quản lý thị trường", "https://hanoi.dms.gov.vn/tin-t%E1%BB%A9c-s%E1%BB%B1-ki%E1%BB%87n", 0),
    ("Cục Quản lý thị trường Hà Nội - Kiểm tra kiểm soát", "Quản lý thị trường", "https://hanoi.dms.gov.vn/kiem-tra-kiem-soat", 0),
    ("Cục Quản lý thị trường Hà Nội - Hoạt động", "Quản lý thị trường", "https://hanoi.dms.gov.vn/hoat-dong", 0)
]

def init_db():
    """Khởi tạo toàn bộ cấu trúc bảng và đồng bộ dữ liệu ban đầu trên PostgreSQL"""
    conn = db_adapter_github.get_conn()
    cursor = db_adapter_github.dict_cursor(conn)
    
    # 1. Tạo bảng raw_articles
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS raw_articles (
            id SERIAL PRIMARY KEY,
            source_type TEXT NOT NULL,
            source_name TEXT NOT NULL,
            title TEXT,
            url TEXT UNIQUE,
            summary TEXT,
            published_date TEXT,
            crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 2. Tạo bảng rss_sources
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rss_sources (
            id SERIAL PRIMARY KEY,
            source_name TEXT NOT NULL,
            category TEXT,
            rss_url TEXT UNIQUE NOT NULL,
            is_active INTEGER DEFAULT 1,
            last_checked TEXT,
            last_error TEXT,
            is_rss INTEGER DEFAULT 1
        )
    ''')
    
    # 3. Tạo bảng classified_articles
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS classified_articles (
            id SERIAL PRIMARY KEY,
            raw_article_id INTEGER UNIQUE NOT NULL,
            domain_id INTEGER NOT NULL,
            match_reason TEXT,
            confidence_score REAL,
            classified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            title TEXT,
            summary TEXT,
            url TEXT,
            classification_status TEXT,
            classifier_model TEXT DEFAULT 'Không',
            human_evaluation INTEGER DEFAULT NULL,
            FOREIGN KEY (raw_article_id) REFERENCES raw_articles (id)
        )
    ''')
    
    # 4. Tạo bảng resolution_keywords
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS resolution_keywords (
            id SERIAL PRIMARY KEY,
            domain_id INTEGER NOT NULL,
            keyword TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 5. Tạo bảng matched_cases
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS matched_cases (
            id SERIAL PRIMARY KEY,
            raw_article_id INTEGER UNIQUE NOT NULL,
            domain_id INTEGER NOT NULL,
            source_name TEXT NOT NULL,
            title TEXT,
            summary TEXT,
            url TEXT UNIQUE,
            match_reason TEXT,
            published_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (raw_article_id) REFERENCES raw_articles (id)
        )
    ''')
    
    conn.commit()
    
    # Nạp từ khóa mặc định nếu trống
    cursor.execute("SELECT COUNT(*) FROM resolution_keywords")
    kw_count = cursor.fetchone()
    # Hỗ trợ cả trả về dict và tuple
    kw_count_val = kw_count["count"] if isinstance(kw_count, dict) else kw_count[0]
    
    if kw_count_val == 0:
        print("🌱 Đang nạp từ khóa pháp lý vào PostgreSQL...")
        DEFAULT_KEYWORDS = [
            (5, "dân tộc thiểu số"), (5, "vùng đồng bào"), (5, "đồng bào thiểu số"), (5, "vùng đặc biệt khó khăn"),
            (5, "trợ giúp pháp lý"), (5, "vùng cao"), (5, "vùng sâu"), (5, "bản làng khó khăn"),
            (5, "xã biên giới"), (5, "đồng bào vùng cao"), (5, "định canh định cư"), (5, "xóa đói giảm nghèo"),
            (5, "chương trình 135"), (5, "phát triển miền núi"), (5, "đồng bào khmer"), (5, "người hmông"),
            (5, "người ba na"), (5, "người ê đê"), (5, "người dao"), (5, "vùng khó khăn"),
            (7, "đầu tư công"), (7, "vốn đầu tư công"), (7, "dự án oda"), (7, "vốn ngân sách"),
            (7, "giải ngân vốn công"), (7, "nguồn vốn công"), (7, "dự án nhóm a"), (7, "công trình công cộng"),
            (7, "đầu tư công trình"), (7, "ngân sách nhà nước"), (7, "kế hoạch đầu tư công"), (7, "đầu tư trung hạn"),
            (7, "chủ trương đầu tư"), (7, "giám sát đầu tư công"), (7, "thất thoát vốn đầu tư"), (7, "lãng phí vốn đầu tư"),
            (7, "nghiệm thu công trình công"), (7, "thầu dự án công"), (7, "giải ngân đầu tư"), (7, "đầu tư hạ tầng"),
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
            (9, "tài nguyên"), (9, "khoáng sản"), (9, "khai thác trái phép"), (9, "cát tặc"),
            (9, "quặng"), (9, "vàng tặc"), (9, "tài nguyên nước"), (9, "tài nguyên rừng"),
            (9, "vùng biển"), (9, "vùng trời"), (9, "kho số"), (9, "tần số vô tuyến"),
            (9, "quỹ đạo vệ tinh"), (9, "dữ liệu số"), (9, "tài nguyên internet"), (9, "khai thác cát lậu"),
            (9, "quặng sắt"), (9, "quặng đồng"), (9, "nước ngầm"), (9, "khai thác đá"),
            (9, "môi trường"), (9, "ô nhiễm"), (9, "xả thải"), (9, "khói bụi"),
            (9, "rác thải"), (9, "chất thải"), (9, "phát thái"), (9, "ô nhiễm nước"),
            (9, "ô nhiễm không khí"), (9, "rác thải công nghiệp"), (9, "chất thải nguy hại"), (9, "xả thải trái phép"),
            (9, "ô nhiễm dòng sông"), (9, "khí thải độc hại"), (9, "sự cố môi trường"), (9, "luật bảo vệ môi trường"),
            (9, "bụi mịn"), (9, "nước thải công nghiệp"), (9, "xử lý chất thải"), (9, "chôn lấp rác thải"),
            (9, "hệ sinh thái"), (9, "đa dạng sinh học"), (9, "rừng đặc dụng"), (9, "rừng phòng hộ"),
            (9, "động vật hoang dã"), (9, "săn bắt lậu"), (9, "săn bắn"), (9, "bảo tồn thiên nhiên"),
            (9, "vườn quốc gia"), (9, "chặt phá rừng"), (9, "phá rừng trái phép"), (9, "lâm tặc"),
            (9, "buôn bán động vật hoang dã"), (9, "sinh vật ngoại lai"), (9, "suy giảm sinh thái"), (9, "bảo tồn đa dạng"),
            (9, "khu dự trữ sinh quyển"), (9, "phá rừng đầu nguồn"), (9, "gỗ lậu"), (9, "động vật quý hiếm"),
            (10, "di sản văn hóa"), (10, "di vật"), (10, "cổ vật"), (10, "bảo vật quốc gia"),
            (10, "di tích lịch sử"), (10, "di tích quốc gia"), (10, "di sản phi vật thể"), (10, "danh lam thắng cảnh"),
            (10, "trùng tu di tích"), (10, "phá hoại di tích"), (10, "xâm hại di tích"), (10, "di sản thế giới"),
            (10, "khu di tích"), (10, "hiện vật lịch sử"), (10, "di chỉ khảo cổ"), (10, "bảo tàng lịch sử"),
            (10, "danh thắng"), (10, "tôn tạo di tích"), (10, "di sản văn hóa vật thể"), (10, "luật di sản"),
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
            (12, "quyền lợi người tiêu dùng"), (12, "bảo vệ người tiêu dùng"), (12, "hàng giả"), (12, "hàng nhái"),
            (12, "lừa đảo tiêu dùng"), (12, "đa cấp biến tướng"), (12, "lừa gạt khách hàng"), (12, "bán hàng giả"),
            (12, "gian lận thương mại"), (12, "cân thiếu"), (12, "hàng kém chất lượng"), (12, "hàng xách tay lậu"),
            (12, "quảng cáo sai sự thật"), (12, "thổi phồng công dụng"), (12, "hợp đồng mẫu lừa dối"), (12, "gian lận xuất xứ"),
            (12, "tem giả"), (12, "bảo hành gian dối"), (12, "hàng trốn thuế"), (12, "sản phẩm khuyết tật")
        ]
        
        for dom_id, keyword in DEFAULT_KEYWORDS:
            try:
                cursor.execute('''
                    INSERT INTO resolution_keywords (domain_id, keyword)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                ''', (dom_id, keyword))
            except Exception:
                conn.rollback()
        conn.commit()
        print("🌱 Đã nạp thành công từ khóa mặc định.")

    # Dọn dẹp nguồn RSS cũ để đồng bộ mới
    try:
        cursor.execute("DELETE FROM rss_sources WHERE (source_name LIKE 'Báo Nhân Dân%' OR rss_url = 'https://baotintuc.vn/rss.htm') AND is_rss = 1")
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"⚠️ Lỗi dọn dẹp RSS cũ: {e}")

    # Đồng bộ danh sách nguồn RSS mặc định
    print("🌱 Đang kiểm tra và đồng bộ danh sách nguồn RSS chất lượng cao...")
    for name, category, url in DEFAULT_SOURCES:
        try:
            cursor.execute('''
                INSERT INTO rss_sources (source_name, category, rss_url, is_active, is_rss)
                VALUES (%s, %s, %s, 1, 1)
                ON CONFLICT (rss_url) DO NOTHING
            ''', (name, category, url))
        except Exception:
            conn.rollback()
    conn.commit()

    # Đồng bộ danh sách nguồn phi RSS
    try:
        cursor.execute("DELETE FROM rss_sources WHERE is_rss = 0")
        conn.commit()
    except Exception:
        conn.rollback()

    print("🌱 Đang kiểm tra và đồng bộ danh sách nguồn cào HTML trực tiếp (không RSS)...")
    for name, category, url, is_rss_val in DEFAULT_NON_RSS_SOURCES:
        try:
            cursor.execute('''
                INSERT INTO rss_sources (source_name, category, rss_url, is_active, is_rss)
                VALUES (%s, %s, %s, 1, %s)
                ON CONFLICT (rss_url) DO NOTHING
            ''', (name, category, url, is_rss_val))
        except Exception:
            conn.rollback()
    conn.commit()
    
    conn.close()
    print("✅ Đã khởi tạo cơ sở dữ liệu PostgreSQL thành công.")

def get_active_rss_sources():
    """Lấy toàn bộ nguồn RSS đang hoạt động"""
    conn = db_adapter_github.get_conn()
    cursor = db_adapter_github.dict_cursor(conn)
    cursor.execute("SELECT id, source_name, category, rss_url, is_active FROM rss_sources WHERE is_active = 1 AND is_rss = 1")
    sources = db_adapter_github.rows_to_dicts(cursor.fetchall())
    conn.close()
    return sources

def get_active_non_rss_sources():
    """Lấy toàn bộ nguồn cào HTML trực tiếp đang hoạt động"""
    conn = db_adapter_github.get_conn()
    cursor = db_adapter_github.dict_cursor(conn)
    cursor.execute("SELECT id, source_name, category, rss_url, is_active FROM rss_sources WHERE is_active = 1 AND is_rss = 0")
    sources = db_adapter_github.rows_to_dicts(cursor.fetchall())
    conn.close()
    return sources

def update_source_status(source_id, last_error=None, is_active=1):
    """Cập nhật trạng thái và nhật ký lỗi của nguồn RSS"""
    conn = db_adapter_github.get_conn()
    cursor = db_adapter_github.dict_cursor(conn)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        UPDATE rss_sources
        SET last_checked = %s, last_error = %s, is_active = %s
        WHERE id = %s
    """, (now, last_error, is_active, source_id))
    conn.commit()
    conn.close()

def filter_new_urls(urls):
    """Lọc ra các URL chưa tồn tại trong bảng raw_articles"""
    if not urls:
        return set()
    conn = db_adapter_github.get_conn()
    cursor = db_adapter_github.dict_cursor(conn)
    chunk_size = 500
    existing_urls = set()
    for i in range(0, len(urls), chunk_size):
        chunk = list(urls[i:i+chunk_size])
        placeholders = ",".join(["%s"] * len(chunk))
        cursor.execute(f"SELECT url FROM raw_articles WHERE url IN ({placeholders})", chunk)
        for row in cursor.fetchall():
            existing_urls.add(row["url"])
    conn.close()
    return set(urls) - existing_urls

def save_articles(articles):
    """Lưu danh sách bài viết vào PostgreSQL bằng Bulk Insert hiệu năng cao"""
    if not articles:
        return 0
        
    conn = db_adapter_github.get_conn()
    cursor = db_adapter_github.dict_cursor(conn)
    count = 0
    
    # Chuẩn bị dữ liệu
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
        from psycopg2.extras import execute_values
        query = """
            INSERT INTO raw_articles (source_type, source_name, title, url, summary, published_date)
            VALUES %s
            ON CONFLICT (url) DO NOTHING
        """
        execute_values(cursor, query, values)
        conn.commit()
        count = len(articles)
    except Exception as e:
        print(f"⚠️ Lỗi bulk insert: {e}. Thử fallback ghi từng dòng...")
        conn.rollback()
        for article in articles:
            try:
                summary_val = article.get('summary') or article.get('content_snippet')
                cursor.execute("""
                    INSERT INTO raw_articles (source_type, source_name, title, url, summary, published_date)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (url) DO NOTHING
                """, (article.get('source_type'), article.get('source_name'),
                       article.get('title'), article.get('url'),
                       summary_val, article.get('published_date')))
                count += 1
            except Exception:
                pass
        conn.commit()
    finally:
        conn.close()
        
    return count

def get_unclassified_articles():
    """Lấy toàn bộ bài viết thô chưa được phân loại"""
    conn = db_adapter_github.get_conn()
    cursor = db_adapter_github.dict_cursor(conn)
    cursor.execute('''
        SELECT id, source_type, source_name, title, url, summary, published_date
        FROM raw_articles
        WHERE id NOT IN (SELECT raw_article_id FROM classified_articles)
    ''')
    rows = db_adapter_github.rows_to_dicts(cursor.fetchall())
    conn.close()
    return rows

def save_classified_article(raw_article_id, domain_id, match_reason, confidence_score, title="", summary="", url="", classification_status="", classifier_model="Không"):
    """Lưu kết quả phân loại bài viết"""
    conn = db_adapter_github.get_conn()
    cursor = db_adapter_github.dict_cursor(conn)
    success = False
    try:
        cursor.execute("""
            INSERT INTO classified_articles
            (raw_article_id, domain_id, match_reason, confidence_score, title, summary, url, classification_status, classifier_model)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (raw_article_id, domain_id, match_reason, confidence_score, title, summary, url, classification_status, classifier_model))
        conn.commit()
        success = True
    except Exception:
        pass
    conn.close()
    return success

def save_classified_articles_batch(records):
    """Lưu hàng loạt kết quả phân loại bằng Batch Transaction trên PostgreSQL"""
    if not records:
        return 0
    conn = db_adapter_github.get_conn()
    cursor = db_adapter_github.dict_cursor(conn)
    count = 0
    try:
        for rec in records:
            try:
                cursor.execute("""
                    INSERT INTO classified_articles
                    (raw_article_id, domain_id, match_reason, confidence_score, title, summary, url, classification_status, classifier_model)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, rec)
                count += 1
            except Exception:
                pass
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"⚠️ Lỗi lưu batch: {e}")
    finally:
        conn.close()
    return count

def get_keywords_from_db():
    """Lấy toàn bộ từ khóa phân loại theo từng lĩnh vực từ CSDL"""
    conn = db_adapter_github.get_conn()
    cursor = db_adapter_github.dict_cursor(conn)
    cursor.execute("SELECT domain_id, keyword FROM resolution_keywords")
    rows = cursor.fetchall()
    conn.close()
    import re
    keywords_dict = {}
    for row in rows:
        dom_id = row["domain_id"]
        keyword = row["keyword"]
        if dom_id not in keywords_dict:
            keywords_dict[dom_id] = []
        keywords_dict[dom_id].append(re.escape(keyword.lower()))
    return keywords_dict

def save_matched_case(raw_article_id, domain_id, source_name, title, summary, url, match_reason, published_date):
    """Lưu vụ việc vi phạm khớp vào bảng matched_cases"""
    conn = db_adapter_github.get_conn()
    cursor = db_adapter_github.dict_cursor(conn)
    success = False
    try:
        cursor.execute("""
            INSERT INTO matched_cases (raw_article_id, domain_id, source_name, title, summary, url, match_reason, published_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (raw_article_id) DO UPDATE SET match_reason=EXCLUDED.match_reason
        """, (raw_article_id, domain_id, source_name, title, summary, url, match_reason, published_date))
        conn.commit()
        success = True
    except Exception:
        pass
    conn.close()
    return success

if __name__ == "__main__":
    init_db()
