# Test cases — Trợ lý Kế hoạch Hàng hoá (AG-INVENTORY-DAYS)

> ⚠️ BẮT BUỘC trước khi code. Mỗi luồng ở USECASE.md có ít nhất 1 case.
> Case chạy tự động: `cd src && python ../tests/test_coc.py` — chạy luôn trong
> Docker build và trong CI, build fail nếu tra cứu sai.

## A. Hỏi — đáp quy trình

| # | Kịch bản | Đầu vào | Kỳ vọng | Tự động |
|---|---|---|---|---|
| 1 | Happy path — có số mục | "chốt PR ngày nào" | Trả nhịp chốt PR, kèm `— CoC KHHH, mục 4.1` | ✅ `test_in_scope` |
| 2 | Câu hỏi đòi con số | "ghép combo phải báo trước mấy ngày" | Trả lời **có con số** (ngày 20 hàng tháng · 5 ngày trước ngày cần lên tồn), mục 4.10 | ✅ `test_in_scope` |
| 3 | Ngưỡng vận hành | "luân chuyển tối thiểu bao nhiêu sản phẩm" | "2 kiện ≈ 48 sản phẩm", mục 4.9 | ✅ `test_in_scope` |
| 4 | Bảng số liệu | "ngày tồn kho mục tiêu của HAPAS Thái Lan" | Đọc được số từ bảng (45 · 85 · ngưỡng cảnh báo), mục 3.2 | ✅ `test_in_scope` |
| 5 | Luôn trích nguồn | mọi câu ở nhóm A | Câu trả lời **luôn** chứa `— CoC KHHH,` | ✅ `test_answer_always_cites_source` |
| 6 | Tự giới thiệu | "em làm được gì?" · "bạn là ai" | Nêu đúng 3 việc đang chạy thật, nói rõ phần nào chưa có dữ liệu | ⬜ thủ công |

## B. Hỏi — đáp tồn kho

| # | Kịch bản | Đầu vào | Kỳ vọng | Tự động |
|---|---|---|---|---|
| 7 | Xếp hạng tồn cao | "top 5 mã tồn cao" | 5 mã kèm số ngày tồn, số lượng, TĐB | ⬜ `python lark_base.py` |
| 8 | Rủi ro hết hàng | "mã nào sắp hết hàng" | Mã có số ngày tồn thấp nhất, chỉ tính mã còn bán | ⬜ `python lark_base.py` |
| 9 | Tra 1 mã cụ thể | gõ hẳn mã SKU | Đúng mã đó, kèm tồn + TĐB + ngày tồn | ⬜ `python lark_base.py --sku` |
| 10 | Vốn chết | "mã nào không bán được" | Mã còn tồn mà TĐB = 0. **Không** hiển thị "0 ngày tồn" (0 ngày nghĩa là sắp hết, ngược hẳn ý nghĩa) | ⬜ thủ công |
| 11 | Chưa nạp dữ liệu | hỏi tồn kho khi chạy không có `--base`/`--excel` | Báo "chưa có dữ liệu", **không bịa số** | ⬜ thủ công |
| 12 | Base lỗi giữa chừng | ngắt mạng rồi hỏi tồn kho | Dùng lại số trong cache, ghi cảnh báo vào log, **không** báo "chưa có dữ liệu" | ⬜ thủ công |

## C. Im lặng đúng lúc

| # | Kịch bản | Đầu vào | Kỳ vọng | Tự động |
|---|---|---|---|---|
| 13 | Ngoài phạm vi | "giá vàng hôm nay bao nhiêu" · "ai vô địch world cup" | **Không trả lời gì cả** | ✅ `test_out_of_scope` |
| 14 | Không được @, không chắc | tin nhắn bâng quơ trong nhóm | Im lặng, không chen vào | ✅ `test_strict_im_lang` |
| 15 | Không được @, tra ra chắc chắn | câu hỏi quy trình rõ ràng | Được phép trả lời | ✅ `test_strict_tra_loi_duoc` |
| 16 | Không lộ thông tin nhạy cảm | mọi câu trả lời | Không chứa app_secret, token, credential | ✅ `test_no_credentials_leaked` |

## D. Vận hành

| # | Kịch bản | Cách thử | Kỳ vọng |
|---|---|---|---|
| 17 | Chạy 2 bản bot | Mở `run_bot.bat` khi đã có bot chạy nền | Bản thứ hai tự thoát, log ghi "Đã có một bản bot đang chạy". **Không** trả lời trùng 2 lần |
| 18 | Mất mạng lúc khởi động | Ngắt mạng rồi bật bot | Retry 10s/lần trong 10 phút, **không** crash-loop. Log 1 dòng gọn, không đổ traceback mỗi 3 giây |
| 19 | Add vào nhóm mới | Add bot vào 1 nhóm bất kỳ | Trong ~1 phút bot tự phát hiện và phục vụ nhóm đó (khi `CHAT_IDS` để trống) |
| 20 | Tài liệu sai | Sửa hỏng `CODE_OF_CONDUCT_KHHH.md` rồi build | Docker build **fail**, không ra được image lỗi |

## Giới hạn đã biết

Case 7–12 và 17–19 hiện **chưa tự động hoá** vì cần credential Lark thật và một
Base có dữ liệu. Đang thử thủ công qua `python lark_base.py` và nhóm `test AI`.
Bước tiếp theo: dựng bản ghi mẫu để test tồn kho chạy được trong CI mà không cần
gọi Lark.
