# -*- coding: utf-8 -*-
import re
import sys
import io
import os
import pickle

# Đảm bảo in tiếng Việt chuẩn trên Windows bằng reconfigure (tránh lỗi đóng stream)
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# TẬP DANH MỤC LĨNH VỰC THEO NGHỊ QUYẾT 205/2025/QH15
REFERENCE_KNOWLEDGE = {
    1: {"name": "Trẻ em (dưới 16 tuổi)"},
    2: {"name": "Người cao tuổi (từ đủ 60 tuổi)"},
    3: {"name": "Người khuyết tật"},
    4: {"name": "Phụ nữ mang thai / Nuôi con dưới 36 tháng"},
    5: {"name": "Dân tộc thiểu số vùng ĐBKK"},
    6: {"name": "Người khó khăn nhận thức / Mất năng lực hành vi dân sự"},
    7: {"name": "Lợi ích công: Đầu tư công"},
    8: {"name": "Lợi ích công: Tài sản công, Đất đai"},
    9: {"name": "Lợi ích công: Môi trường, Hệ sinh thái"},
    10: {"name": "Lợi ích công: Di sản văn hóa"},
    11: {"name": "Lợi ích công: An toàn thực phẩm, Dược phẩm"},
    12: {"name": "Lợi ích công: Bảo vệ quyền lợi người tiêu dùng"}
}

# =====================================================================
# BỘ TỪ ĐIỂN 600+ TỪ KHÓA PHÁP LÝ ĐẶC TRỊ CHO 12 LĨNH VỰC NGHỊ QUYẾT 205/2025/QH15
# Nhúng trực tiếp để tránh hoàn toàn lỗi Mojibake đường dẫn tiếng Việt của Windows
# =====================================================================
LEGAL_REGEX_KEYWORDS = {
    # 1. Trẻ em
    1: [
        "bạo hành trẻ em", "xâm hại trẻ em", "ngược đãi trẻ em", "đánh đập trẻ em", 
        "dụ dỗ trẻ em", "lôi kéo trẻ em", "bắt cóc trẻ em", "mua bán trẻ em", 
        "chiếm đoạt trẻ em", "giao cấu với trẻ em", "giao cấu với người dưới 16 tuổi", 
        "dâm ô đối với người dưới 16 tuổi", "xâm hại tình dục trẻ em", "sử dụng lao động trẻ em", 
        "bóc lột sức lao động trẻ em", "cưỡng bức lao động trẻ em", "bạo lực học đường", 
        "đánh đập học sinh", "bạo hành học sinh", "bảo mẫu bạo hành", "cha dượng bạo hành", 
        "mẹ kế bạo hành", "tra tấn trẻ em", "hành hạ trẻ em", "bỏ rơi trẻ em", 
        "bỏ rơi trẻ sơ sinh", "đẻ rơi", "vứt bỏ con mới sinh", "đánh đập con ruột", 
        "ép buộc trẻ xin ăn", "ép buộc trẻ ăn xin", "lạm dụng tình dục trẻ em", 
        "phát tán văn hóa phẩm đồi trụy trẻ em", "xúi giục trẻ em phạm tội", "dụ dỗ trẻ em phạm pháp", 
        "bắt trẻ em làm việc độc hại", "không cho trẻ em đi học", "cản trở quyền học tập của trẻ", 
        "ngược đãi con đẻ", "ngược đãi con nuôi", "ngược đãi con riêng", "bạo lực gia đình với trẻ", 
        "cha mẹ bạo hành con", "giáo viên bạo hành", "đánh đập bé trai", "hành hạ bé gái", 
        "xâm hại nữ sinh", "học sinh lớp 1 bị đánh", "học sinh tiểu học bị ngược đãi", "bắt giữ trẻ em trái pháp luật"
    ],
    # 2. Người cao tuổi
    2: [
        "ngược đãi người cao tuổi", "ngược đãi người già", "ngược đãi cha mẹ", "ngược đãi ông bà", 
        "bỏ rơi người cao tuổi", "bỏ rơi cha mẹ già", "bỏ rơi ông bà già", "đánh đập người cao tuổi", 
        "đánh đập người già", "đánh đập cha mẹ", "đánh đập ông bà", "hành hạ cha mẹ già", 
        "hành hạ ông bà già", "lăng mạ cha mẹ già", "chửi bới cha mẹ già", "xúc phạm nhân phẩm người cao tuổi", 
        "xúc phạm nhân phẩm người già", "xúc phạm nhân phẩm cha mẹ", "ép buộc người cao tuổi lao động", 
        "ép buộc người già lao động", "bóc lột sức lao động người già", "chiếm đoạt tài sản người cao tuổi", 
        "chiếm đoạt tài sản người già", "chiếm đoạt tiền dưỡng già", "lừa đảo chiếm đoạt tài sản người già", 
        "lừa tiền người cao tuổi", "lừa tiền người già", "cướp tài sản người già", 
        "trộm tài sản người già", "giam giữ người cao tuổi", "nhốt người già", "bạo hành người già", 
        "bạo hành người cao tuổi", "bạo hành cha mẹ già", "bạo hành ông bà già", "ngược đãi cụ già", 
        "bỏ mặc người già", "không phụng dưỡng cha mẹ", "từ chối phụng dưỡng cha mẹ", "đùn đẩy việc nuôi dưỡng cha mẹ", 
        "đuổi cha mẹ ra khỏi nhà", "đuổi người già ra khỏi nhà", "bạo lực gia đình với người già", "cụ ông bị bạo hành", 
        "cụ bà bị bạo hành", "người cao tuổi bị đánh", "người già bị bạo lực", "ngược đãi người già yếu", 
        "ngược đãi người trên 60 tuổi", "chiếm đoạt đất của cha mẹ"
    ],
    # 3. Người khuyết tật
    3: [
        "kỳ thị người khuyết tật", "phân biệt đối xử người khuyết tật", "ngược đãi người khuyết tật", "đánh đập người khuyết tật", 
        "hành hạ người khuyết tật", "xúc phạm người khuyết tật", "bạo hành người khuyết tật", "ăn chặn tiền người khuyết tật", 
        "ăn chặn tiền trợ cấp khuyết tật", "ăn chặn trợ cấp xã hội", "chiếm đoạt tiền khuyết tật", "cắt xén tiền khuyết tật", 
        "bóc lột người khuyết tật", "bóc lột sức lao động người khuyết tật", "ép buộc người khuyết tật ăn xin", "ép buộc người khuyết tật xin ăn", 
        "chăn dắt người khuyết tật", "lợi dụng người khuyết tật để trục lợi", "không đảm bảo quyền lợi người khuyết tật", "vi phạm chế độ người khuyết tật", 
        "ngược đãi người tàn tật", "đánh đập người tàn tật", "bạo hành người tàn tật", "kỳ thị người tàn tật", 
        "ngược đãi người câm", "ngược đãi người điếc", "ngược đãi người mù", "bóc lột người câm điếc", 
        "bạo lực với người khuyết tật", "lăng mạ người khuyết tật", "ngược đãi trẻ em khuyết tật", "bạo hành trẻ khuyết tật", 
        "cơ sở khuyết tật bạo hành", "trung tâm bảo trợ bạo hành", "ăn chặn tiền từ thiện khuyết tật", "chiếm đoạt quà từ thiện khuyết tật", 
        "sa thái người khuyết tật trái luật", "không tuyển dụng người khuyết tật vì kỳ thị", "từ chối nhận người khuyết tật trái phép", "bạo lực gia đình với người khuyết tật", 
        "nhốt người khuyết tật", "giam giữ người khuyết tật", "ngược đãi người khuyết tật nặng", "ngược đãi người chất độc da cam", 
        "người khuyết tật bị đánh", "người khuyết tật bị ngược đãi", "người tàn tật bị bạo hành", "người câm bị bạo hành", 
        "người mù bị lừa đảo", "trục lợi từ người khuyết tật"
    ],
    # 4. Phụ nữ mang thai hoặc nuôi con dưới 36 tháng
    4: [
        "sa thái phụ nữ mang thai", "sa thái thai phụ", "sa thái phụ nữ nuôi con nhỏ", "sa thái phụ nữ nuôi con dưới 36 tháng", 
        "chấm dứt hợp đồng phụ nữ mang thai", "chấm dứt hợp đồng thai phụ", "chấm dứt hợp đồng phụ nữ nuôi con nhỏ", "đuổi việc phụ nữ mang thai", 
        "đuổi việc thai phụ", "đuổi việc phụ nữ nuôi con dưới 36 tháng", "cắt giảm phụ nữ mang thai", "không trả lương thai sản", 
        "ăn chặn tiền thai sản", "quỵt tiền thai sản", "không đóng bảo hiểm thai sản", "ép phụ nữ mang thai làm việc độc hại", 
        "ép thai phụ làm việc nặng nhọc", "bắt phụ nữ mang thai làm ca đêm", "bắt phụ nữ mang thai làm thêm giờ", "bạo hành phụ nữ mang thai", 
        "bạo hành thai phụ", "đánh đập phụ nữ mang thai", "đánh đập thai phụ", "hành hạ phụ nữ mang thai", 
        "ngược đãi phụ nữ mang thai", "ngược đãi thai phụ", "bạo lực gia đình với phụ nữ mang thai", "bạo lực gia đình với thai phụ", 
        "chồng đánh vợ mang thai", "chồng đánh vợ nuôi con nhỏ", "đánh đập phụ nữ nuôi con dưới 36 tháng", "bạo hành phụ nữ nuôi con dưới 36 tháng", 
        "ngược đãi phụ nữ nuôi con nhỏ", "bạo hành mẹ bỉm sữa", "đánh đập mẹ bỉm sữa", "sa thái sản phụ trái luật", 
        "buộc thôi việc phụ nữ mang thai", "phân biệt đối xử phụ nữ mang thai", "từ chối nhận phụ nữ mang thai", "từ chối chế độ thai sản", 
        "cắt xén quyền lợi thai sản", "bạo lực tinh thần phụ nữ mang thai", "ép phụ nữ mang thai nghỉ việc", "ép thai phụ nghỉ việc", 
        "phụ nữ mang thai bị đánh", "phụ nữ mang thai bị bạo hành", "thai phụ bị bạo lực", "mẹ nuôi con dưới 36 tháng bị đánh", 
        "mẹ nuôi con nhỏ bị bạo hành", "ngược đãi sản phụ"
    ],
    # 5. Dân tộc thiểu số vùng đặc biệt khó khăn
    5: [
        "miệt thị dân tộc", "kỳ thị dân tộc", "chia rẽ dân tộc", "phân biệt chủng tộc", 
        "phân biệt đối xử dân tộc", "xúc phạm đồng bào dân tộc", "miệt thị người dân tộc", "kỳ thị người dân tộc", 
        "tuyên truyền chia rẽ dân tộc", "phá hoại chính sách đoàn kết dân tộc", "lừa đảo đồng bào dân tộc", "lừa tiền người dân tộc", 
        "lừa đất người dân tộc", "chiếm đoạt đất của đồng bào dân tộc", "cướp đất người dân tộc", "lừa gạt người dân tộc thiểu số", 
        "lợi dụng người dân tộc để trục lợi", "ăn chặn tiền hỗ trợ dân tộc", "ăn chặn tiền xóa đói giảm nghèo", "cắt xén tiền hỗ trợ dân tộc", 
        "tham nhũng quỹ hỗ trợ dân tộc", "chiếm đoạt tiền hỗ trợ vùng cao", "lừa đảo vùng đồng bào dân tộc", "lừa gạt đồng bào thiểu số", 
        "bóc lột đồng bào dân tộc", "cưỡng bức lao động người dân tộc", "lừa bán phụ nữ dân tộc", "mua bán người dân tộc thiểu số", 
        "dụ dỗ phụ nữ dân tộc ra nước ngoài", "lừa bán phụ nữ vùng cao", "ép buộc kết hôn vùng dân tộc", "tuyên truyền tà đạo vùng dân tộc", 
        "lợi dụng tôn giáo chia rẽ dân tộc", "kích động biểu tình vùng dân tộc", "gây rối an ninh vùng dân tộc", "phá hoại tài sản người dân tộc", 
        "phân biệt đối xử học sinh dân tộc", "kỳ thị học sinh vùng cao", "người dân tộc bị lừa đảo", "đồng bào dân tộc bị chiếm đoạt đất", 
        "người dân tộc thiểu số bị ngược đãi", "đồng bào vùng cao bị lừa", "người Hmông bị lừa", "người Khơ-me bị lừa", 
        "người Ê-đê bị lừa", "người Gia-rai bị lừa", "lừa gạt người Chăm", "cắt xén chính sách hỗ trợ vùng cao", 
        "ăn chặn tiền dự án 135", "tham nhũng chính sách dân tộc"
    ],
    # 6. Người khó khăn nhận thức / Mất năng lực hành vi dân sự
    6: [
        "lừa đảo người tâm thần", "lừa đảo người điên", "lừa đảo người mất năng lực hành vi", "chiếm đoạt tài sản người tâm thần", 
        "chiếm đoạt tài sản người mất năng lực", "ép người tâm thần ký hợp đồng", "ép người tâm thần ký giấy bán đất", "lừa người tâm thần bán nhà", 
        "lừa người mất năng lực hành vi bán đất", "lừa người hạn chế nhận thức ký giấy", "trộm tài sản người tâm thần", "cướp tài sản người tâm thần", 
        "ngược đãi người tâm thần", "đánh đập người tâm thần", "bạo hành người tâm thần", "hành hạ người tâm thần", 
        "xúc phạm người tâm thần", "nhốt người tâm thần", "giam giữ người tâm thần", "xích chân người tâm thần", 
        "trói người tâm thần", "bỏ rơi người tâm thần", "ngược đãi người mất năng lực hành vi", "bạo hành người mất năng lực hành vi", 
        "nhốt người mất năng lực hành vi", "lợi dụng người tâm thần để trục lợi", "lợi dụng người tâm thần phạm tội", "xúi giục người tâm thần phạm pháp", 
        "ép người tâm thần đi ăn xin", "chăn dắt người tâm thần", "ăn chặn tiền trợ cấp người tâm thần", "cắt xén tiền bảo trợ xã hội người tâm thần", 
        "ngược đãi người bệnh tâm thần", "bạo hành bệnh nhân tâm thần", "cơ sở bảo trợ ngược đãi người tâm thần", "bệnh viện tâm thần hành hạ người bệnh", 
        "giam giữ người mất năng lực hành vi dân sự", "lạm dụng người khó khăn trong nhận thức", "lừa đảo người khó khăn nhận thức", "chiếm đoạt tài sản người khó khăn nhận thức", 
        "lợi dụng người mất trí nhớ", "lừa đảo người mất trí nhớ", "ép người mất trí nhớ ký giấy", "ngược đãi người thiểu năng", 
        "lừa đảo người thiểu năng", "chiếm đoạt tài sản người thiểu năng", "người tâm thần bị đánh", "người tâm thần bị xích", 
        "người tâm thần bị lừa đất", "người mất năng lực hành vi bị bạo hành"
    ],
    # 7. Đầu tư công
    7: [
        "thất thoát đầu tư công", "lãng phí đầu tư công", "sai phạm đầu tư công", "sai phạm dự án đầu tư công", 
        "thông thầu dự án", "thông thầu đầu tư công", "gian lận thầu", "quây thầu", 
        "thông đồng đấu thầu", "nâng khống giá trị công trình", "nâng khống quyết toán", "nghiệm thu khống", 
        "thi công thiếu khối lượng", "rút ruột công trình", "rút ruột dự án", "tham nhũng đầu tư công", 
        "nhận hối lộ dự án công", "đưa hối lộ dự án công", "chỉ định thầu trái phép", "chia nhỏ gói thầu", 
        "sai phạm giải ngân vốn đầu tư công", "chậm trễ giải ngân gây lãng phí", "gây thất thoát vốn nhà nước", "thất thoát ngân sách nhà nước", 
        "sai phạm quản lý vốn dự án", "dự án công trình đắp chiếu", "công trình lãng phí", "sai phạm thi công công trình công", 
        "sử dụng vật liệu kém chất lượng tại công trình công", "sập công trình công cộng", "nứt cầu đường vốn ngân sách", "dự án nghìn tỷ bỏ hoang", 
        "lãng phí nghìn tỷ", "thất thoát nghìn tỷ", "sai phạm dự án ODA", "thất thoát vốn ODA", 
        "lãng phí vốn ODA", "tham nhũng vốn ODA", "sai phạm ban quản lý dự án", "cựu giám đốc ban quản lý dự án bị bắt", 
        "bắt giam chủ đầu tư dự án công", "khởi tố sai phạm thầu", "sai phạm tại dự án giao thông công cộng", "thông đồng nâng khống giá thiết bị", 
        "nâng giá thiết bị y tế vốn ngân sách", "nâng khống giá thiết bị giáo dục", "thất thoát tài sản nhà nước tại dự án", "sai phạm đấu thầu thiết bị trường học", 
        "sai phạm đấu thầu thiết bị y tế", "lợi dụng chức vụ quyền hạn trong đấu thầu"
    ],
    # 8. Tài sản công, Đất đai
    8: [
        "lấn chiếm đất công", "sử dụng sai mục đích đất công", "tự ý bán đất công", "tự ý thuê đất công", 
        "chiếm đoạt đất công", "lấn chiếm đất công ích", "sử dụng đất công ích trái phép", "phù phép đất công thành đất tư", 
        "xẻ thịt đất công", "thất thoát đất công", "lãng phí đất công", "giao đất công trái luật", 
        "giao đất công không đấu giá", "giao đất không thu tiền trái quy định", "tự ý thanh lý tài sản công", "thanh lý xe công trái quy định", 
        "sử dụng xe công sai mục đích", "lãng phí xe công", "sai phạm đất đai", "sai phạm quản lý đất đai", 
        "giao đất trái thẩm quyền", "cho thuê đất trái thẩm quyền", "thu hồi đất trái quy định", "cưỡng chế đất trái pháp luật", 
        "xẻ thịt rừng phòng hộ", "xẻ thịt rừng đặc dụng", "lấn chiếm đất rừng", "lấn chiếm hành lang an toàn giao thông", 
        "xây dựng trái phép trên đất nông nghiệp", "xây dựng trái phép trên đất công", "biến tướng đất công cộng", "xây chung cư trên đất trường học", 
        "chiếm đoạt công sản", "thất thoát tài sản công", "lãng phí tài sản công", "sai phạm quản lý tài sản công", 
        "nhà đất công sản bị bán rẻ", "bán rẻ đất công", "bán rẻ tài sản nhà nước", "sai phạm chuyển đổi mục đích sử dụng đất", 
        "chuyển đổi đất công viên thành chung cư", "lấn chiếm bờ sông", "lấn chiếm vỉa hè trái phép", "chiếm đoạt đất công viên", 
        "bắt giam cán bộ đất đai", "khởi tố sai phạm quản lý đất", "phân lô bán nền trên đất công", "tự ý phân lô bán nền trái phép", 
        "cựu chủ tịch xã giao đất trái luật", "chiếm dụng nhà công vụ"
    ],
    # 9. Môi trường, Hệ sinh thái
    9: [
        "xả thải trái phép", "xả thải không qua xử lý", "xả trực tiếp ra dòng sông", "xả thải độc hại", 
        "chôn lấp chất thải nguy hại", "chôn lấp rác thải nguy hại trái phép", "đổ trộm chất thải", "đổ trộm bùn thải", 
        "đổ trộm hóa chất", "ô nhiễm nguồn nước", "ô nhiễm dòng sông", "ô nhiễm không khí", 
        "ô nhiễm tiếng ồn", "ô nhiễm nghiêm trọng", "khai thác cát tặc", "khai thác cát lậu", 
        "cát tặc hoành hành", "cát tặc lộng hành", "khai thác cát trái phép", "sạt lở bờ sông do cát tặc", 
        "phá rừng đầu nguồn", "phá rừng phòng hộ", "phá rừng đặc dụng", "khai thác gỗ lậu", 
        "lâm tặc hoành hành", "lâm tặc tàn phá rừng", "chặt hạ cây cổ thụ", "buôn bán động vật hoang dã", 
        "săn bắt động vật quý hiếm", "buôn bán ngà voi", "buôn bán sừng tê giác", "buôn bán tê tê", 
        "vận chuyển lâm sản trái phép", "hủy hoại môi trường", "gây sự cố môi trường", "xả khói bụi ô nhiễm", 
        "bụi mịn vượt ngưỡng", "chôn lấp rác thải y tế trái phép", "ô nhiễm kênh rạch", "cá chết hàng loạt do xả thải", 
        "khai thác khoáng sản trái phép", "khai thác quặng lậu", "khai thác vàng tặc", "phá hủy hệ sinh thái", 
        "lấn chiếm vùng lõi di sản thiên nhiên", "chặt phá rừng tự nhiên", "hủy hoại san hô", "đánh bắt bằng thuốc nổ", 
        "đánh bắt bằng kích điện", "hủy hoại tài nguyên sinh vật"
    ],
    # 10. Di sản văn hóa
    10: [
        "xâm hại di tích", "xâm hại di sản", "tàn phá di tích", "phá hoại di tích", 
        "đập phá di tích", "di tích bị lấn chiếm", "lấn chiếm khu vực bảo vệ di tích", "xây dựng trái phép tại di tích", 
        "xây dựng trái phép lấn chiếm danh lam thắng cảnh", "trùng tu di tích sai lệch", "trùng tu làm biến dạng di tích", "tự ý sửa chữa di tích quốc gia", 
        "tô vẽ di tích", "quét sơn di tích trái phép", "trùng tu không phép", "tàn phá danh lam thắng cảnh", 
        "xâm hại vùng lõi danh lam thắng cảnh", "đào trộm cổ vật", "đào trộm mộ cổ", "ăn cắp cổ vật", 
        "trộm cắp cổ vật", "trộm bảo vật quốc gia", "buôn bán cổ vật trái phép", "vận chuyển cổ vật lậu", 
        "xuất khẩu cổ vật trái phép", "hủy hoại di chỉ khảo cổ", "đập phá hiện vật lịch sử", "bảo vật quốc gia bị mất cắp", 
        "xâm hại di sản văn hóa vật thể", "xâm hại di sản thiên nhiên thế giới", "phá hoại cảnh quan di tích", "xây dựng kiên cố trên đỉnh núi di sản", 
        "xây nhà hàng trong vùng di tích", "tự ý đập phá cổng đình", "đập phá cổng đền cổ", "hạ giải đình chùa trái phép", 
        "tự ý hạ giải di tích", "bán rẻ cổ vật trong chùa", "trộm chuông đồng cổ", "trộm tượng phật cổ", 
        "làm giả cổ vật lừa đảo", "xâm phạm lăng mộ cổ", "xâm hại bia đá cổ", "tàn phá bia tiến sĩ", 
        "đập phá tháp cổ", "xâm hại thánh địa Mỹ Sơn", "xâm hại vùng đệm Tràng An", "lấn chiếm vịnh Hạ Long trái phép", 
        "hủy hoại di tích cách mạng", "di tích lịch sử bị bỏ hoang tàn phá"
    ],
    # 11. An toàn thực phẩm, Dược phẩm
    11: [
        "sản xuất thực phẩm bẩn", "thực phẩm bẩn chứa hóa chất", "tẩm hóa chất cấm", "ngộ độc thực phẩm tập thể", 
        "hàng trăm người ngộ độc", "học sinh ngộ độc thực phẩm", "công nhân ngộ độc thực phẩm", "ngộ độc bếp ăn tập thể", 
        "dùng thịt thối làm giò chả", "thịt heo nái ngâm hóa chất", "sử dụng hàn the trong thực phẩm", "sử dụng formol bảo quản", 
        "chất tạo nạc trong chăn nuôi", "chất cấm trong chăn nuôi", "dùng hóa chất thúc chín trái cây", "ngâm hóa chất ép chín", 
        "ngộ độc rượu độc", "ngộ độc rượu chứa methanol", "rượu chứa độc tố nguy hại", "sản xuất thuốc giả", 
        "buôn bán thuốc giả", "buôn bán vắc xin giả", "kinh doanh thuốc giả", "thuốc điều trị ung thư giả", 
        "thuốc giả kém chất lượng", "vắc xin giả kém chất lượng", "nhập lậu thuốc tây", "thuốc lậu không rõ nguồn gốc", 
        "kinh doanh dược liệu giả", "dược liệu tẩm lưu huỳnh vượt ngưỡng", "thuốc đông y trộn tân dược cấm", "thực phẩm chức năng giả", 
        "thực phẩm chức năng trộn chất cấm", "cơ sở sản xuất thuốc đông y chui", "sản xuất thuốc tân dược giả quy mô lớn", "mỹ phẩm giả gây hỏng da", 
        "sản xuất mỹ phẩm giả chứa corticoid", "kem trộn chứa chất cấm", "ngộ độc trà sữa", "thịt bò giả làm từ thịt lợn sề", 
        "sử dụng chất tẩy trắng trong bún", "ngâm chất tẩy trắng", "sản xuất nước uống đóng chai giả", "nhiễm khuẩn e coli nghiêm trọng", 
        "phun thuốc trừ sâu cận ngày thu hoạch", "dùng hóa chất cấm trong thủy sản", "bơm tạp chất vào tôm", "bơm rau câu vào tôm để tăng trọng", 
        "sử dụng dầu ăn bẩn tái chế", "cơ sở mổ lợn bệnh dịch tả"
    ],
    # 12. Bảo vệ quyền lợi người tiêu dùng
    12: [
        "sản xuất hàng giả", "sản xuất hàng nhái", "buôn bán hàng giả", "buôn bán hàng nhái", 
        "tiêu thụ hàng giả", "tiêu thụ hàng nhái", "sản xuất hàng giả nhái nhãn hiệu", "giả mạo thương hiệu", 
        "nhái nhãn hiệu", "lừa đảo đa cấp", "kinh doanh đa cấp biến tướng", "đa cấp lừa đảo chiếm đoạt tài sản", 
        "lừa đảo qua mạng", "lừa đảo mua sắm online", "chiêu trò lừa đảo người tiêu dùng", "quảng cáo sai sự thật", 
        "thổi phồng công dụng sản phẩm", "thổi phồng công dụng thực phẩm chức năng", "lừa dối người tiêu dùng", "gian lận thương mại", 
        "cân thiếu hàng hóa", "đong thiếu xăng dầu", "gắn chip gian lận cây xăng", "cột bơm xăng gắn chip", 
        "sử dụng hợp đồng mẫu lừa dối", "áp đặt điều khoản bất lợi cho người mua", "bán sản phẩm khuyết tật nguy hiểm", "sản phẩm lỗi gây cháy nổ", 
        "điện thoại nổ gây thương tích", "xe máy bị lỗi động cơ không thu hồi", "trốn tránh nghĩa vụ bảo hành", "từ chối bảo hành sản phẩm lỗi", 
        "bán hàng xách tay lậu", "bán hàng trốn thuế", "gian lận xuất xứ", "giả mạo xuất xứ Việt Nam", 
        "hàng Trung Quốc đội lốt hàng Việt", "gian lận nhãn mác", "tem chống giả giả", "bán hàng hết hạn sử dụng", 
        "cố ý tẩy xóa hạn sử dụng", "phạt doanh nghiệp gian lận", "lừa đảo bán đất nền dự án ma", "lừa đảo đặt cọc mua nhà", 
        "sàn giao dịch lừa đảo", "lừa gạt người mua hàng", "bán thiết bị tiết kiệm điện lừa đảo", "thổi phồng công nghệ tiết kiệm xăng", 
        "bẫy tài chính người tiêu dùng", "điều khoản mập mờ trong hợp đồng bảo hiểm"
    ]
}

# Biên dịch sẵn (Pre-compile) 600 từ khóa Regex duy nhất 1 lần để tối ưu hóa hiệu năng gấp 50 lần
PRECOMPILED_SNAKE_CASE_PATTERNS = []
for did, keywords in LEGAL_REGEX_KEYWORDS.items():
    sorted_keys = sorted(keywords, key=len, reverse=True)
    for kw in sorted_keys:
        kw_snake = kw.replace(" ", "_")
        pattern = re.compile(r'\b' + re.escape(kw) + r'\b')
        PRECOMPILED_SNAKE_CASE_PATTERNS.append((pattern, kw_snake))

def transform_to_snake_case(text):
    """
    Chuyển đổi các cụm từ khóa pháp lý sang dạng snake_case bằng bộ Regex đã biên dịch sẵn
    """
    text_lower = text.lower()
    for pattern, kw_snake in PRECOMPILED_SNAKE_CASE_PATTERNS:
        text_lower = pattern.sub(kw_snake, text_lower)
    return text_lower

class TfidfSemanticMatcher:
    def __init__(self):
        """
        Khởi tạo Bộ phân loại lai (Hybrid Classifier):
        1. Nạp mô hình Logistic Regression đã huấn luyện trên 100.800 câu phái sinh.
        2. Nếu chưa có mô hình pkl, tự động chuyển về chế độ quét Siêu Regex thuần túy.
        """
        self.regex_patterns = {}
        self.domain_ids = list(REFERENCE_KNOWLEDGE.keys())
        
        # Biên dịch sẵn cụm Regex cho mục đích tìm kiếm giải thích (Explainability) và Fallback
        for did in self.domain_ids:
            keywords = LEGAL_REGEX_KEYWORDS.get(did, [])
            if keywords:
                sorted_keywords = sorted(keywords, key=len, reverse=True)
                pattern_str = r'\b(' + '|'.join([re.escape(k) for k in sorted_keywords]) + r')\b'
                self.regex_patterns[did] = re.compile(pattern_str, re.IGNORECASE)
                
        # Thử nạp mô hình Máy học đã đóng gói
        self.use_ml_model = False
        if os.path.exists("vectorizer.pkl") and os.path.exists("logistic_model.pkl"):
            try:
                with open("vectorizer.pkl", "rb") as f:
                    self.vectorizer = pickle.load(f)
                with open("logistic_model.pkl", "rb") as f:
                    self.model = pickle.load(f)
                self.use_ml_model = True
                print("🔑 [MÔ HÌNH LAI]: Đã nạp thành công mô hình Máy học (100.800 dữ liệu) từ file PKL!")
            except Exception as e:
                print(f"⚠️ Lỗi nạp file pkl: {e}. Hệ thống tự động kích hoạt Fallback Siêu Regex.")
        else:
            print("🔌 [MÔ HÌNH LAI]: Chưa phát hiện file mô hình PKL. Kích hoạt chế độ Siêu Regex thuần túy.")

    def predict(self, title, summary, threshold=0.30):
        """
        Dự đoán bài viết có vi phạm hay không bằng Máy học hoặc Regex Fallback.
        """
        text_raw = f"{title} {summary}"
        
        # CHẾ ĐỘ 1: SỬ DỤNG MÔ HÌNH MÁY HỌC LOGISTIC REGRESSION (ĐÃ HUẤN LUYỆN)
        if self.use_ml_model:
            text_normalized = transform_to_snake_case(text_raw)
            vec = self.vectorizer.transform([text_normalized])
            score = self.model.predict_proba(vec)[0][1]
            
            # Quét tìm bằng chứng từ khóa phục vụ cho Báo cáo (Explainability)
            matched_domain_id = 0
            matched_keywords = []
            for did, pattern in self.regex_patterns.items():
                found = pattern.findall(text_raw.lower())
                if found:
                    matched_domain_id = did
                    matched_keywords = list(set([k.strip() for k in found]))
                    break
            
            is_matched = (score >= threshold) and (matched_domain_id > 0)
            
            if is_matched:
                matched_name = REFERENCE_KNOWLEDGE[matched_domain_id]["name"]
                reason = f"ML-Prob ({score:.2f}): Khớp '{matched_name}' (Từ khóa: {', '.join(matched_keywords[:3])})"
                return True, matched_domain_id, reason, score
            else:
                reason = f"ML Safe ({score:.2f}): Xác suất vi phạm thấp hoặc không khớp từ khóa lĩnh vực"
                return False, 0, reason, score

        # CHẾ ĐỘ 2: FALLBACK SIÊU REGEX THUẦN TÚY (NẾU CHƯA CÓ PKL)
        else:
            text_lower = text_raw.lower()
            PR_WORDS = [
                "ưu đãi", "khuyến mãi", "tri ân", "chào đón", "khai trương", "khánh thành",
                "kỷ niệm", "vinh danh", "trao giải", "bổ nhiệm", "ký kết", "hợp tác",
                "đại hội", "thi đua", "văn nghệ", "thể thao", "bóng đá", "vô địch",
                "giảm giá", "voucher", "trúng thưởng", "quà tặng", "khai mạc"
            ]
            
            is_pr = False
            matched_pr_word = ""
            for pr_w in PR_WORDS:
                if re.search(r'\b' + re.escape(pr_w) + r'\b', text_lower):
                    is_pr = True
                    matched_pr_word = pr_w
                    break
            
            matches = []
            for did, pattern in self.regex_patterns.items():
                found_keywords = pattern.findall(text_lower)
                if found_keywords:
                    unique_keywords = list(set([k.strip() for k in found_keywords]))
                    raw_score = 0.50 + 0.10 * (len(unique_keywords) - 1)
                    raw_score = min(raw_score, 1.0)
                    
                    final_score = raw_score
                    if is_pr:
                        final_score = raw_score * 0.2
                        
                    matches.append({
                        "domain_id": did,
                        "score": final_score,
                        "keywords": unique_keywords
                    })
                    
            if matches:
                matches.sort(key=lambda x: x["score"], reverse=True)
                best_match = matches[0]
                best_did = best_match["domain_id"]
                best_score = best_match["score"]
                best_keywords = best_match["keywords"]
                
                matched_name = REFERENCE_KNOWLEDGE[best_did]["name"]
                evidence = ", ".join(best_keywords[:3])
                
                if is_pr:
                    reason = f"Regex-Match-PR ({best_score:.2f}): Bị phạt PR ('{matched_pr_word}'). Khớp '{matched_name}' (Từ khóa: {evidence})"
                else:
                    reason = f"Regex-Match ({best_score:.2f}): Khớp '{matched_name}' (Từ khóa: {evidence})"
                    
                return best_score >= threshold, best_did, reason, best_score
                
            return False, 0, "Không khớp bất kỳ từ khóa pháp lý nào", 0.0

if __name__ == "__main__":
    matcher = TfidfSemanticMatcher()
    
    # Chạy thử tin bạo hành
    is_match, did, reason, score = matcher.predict(
        "Bạo hành học sinh dã man tại lớp học tư thục",
        "Công an vừa vào cuộc làm rõ vụ việc giáo viên bảo mẫu bạo hành bé trai dưới 16 tuổi gây thương tích."
    )
    print("\n[TEST]")
    print(f"👉 Khớp: {is_match} | Điểm: {score:.2f} | Lý do: {reason}")
