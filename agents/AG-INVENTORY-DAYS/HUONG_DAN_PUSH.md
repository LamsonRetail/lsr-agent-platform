# Hướng dẫn đưa tính năng mới lên GitHub

Dán file này vào phiên Claude mới là làm được ngay. Repo:
`LamsonRetail/lsr-agent-platform` · nhánh `PLANNING` · agent `AG-INVENTORY-DAYS`

---

## Câu dán vào phiên Claude mới

> Tôi là Thảo, KHHH của Lam Son Retail. Agent của tôi ở
> `C:\Users\admin\Downloads\AI Agent\lsr-agent-platform\agents\AG-INVENTORY-DAYS`.
> Đọc `HUONG_DAN_PUSH.md` trong thư mục đó trước khi sửa bất cứ file nào.
> Việc cần làm: <mô tả tính năng>

---

## Quy trình 5 bước

### 1. Dừng bot trước khi sửa

Bấm đúp `bot_nen_STOP.bat`. Chờ ~15 giây, mở `bot_log.txt` thấy dòng
`da dung theo yeu cau` mới làm tiếp.

> ⚠️ **Không sửa file `.bat` khi nó đang chạy.** cmd.exe đọc batch theo vị trí byte;
> ghi đè giữa chừng làm lệch luồng thực thi — bot chạy bằng bản cũ mà không ai biết.

### 2. Sửa code

Chỉ được đụng trong `agents/AG-INVENTORY-DAYS/`. Xem mục "Vùng cấm" bên dưới.

### 3. Chạy test — bắt buộc

```
cd src
python ../tests/test_coc.py
```

Phải xanh hết. Đỏ thì sửa, **đừng push**. Docker build và CI đều chạy đúng test này.

Có sửa phần tồn kho thì thử thêm:
```
python lark_base.py
```

### 4. Push

Bấm đúp `push_to_github.bat`. Script tự: pull → chuyển nhánh PLANNING → commit →
push. Xem `push_log.txt` nếu cần biết chi tiết.

> Sửa message commit trong `push_to_github.bat` (dòng `git commit -m`) cho khớp
> việc vừa làm. Message đang hardcode, không tự đổi.

### 5. PR

Code tự vào **PR #32** đang mở (`PLANNING` → `main`), không cần tạo PR mới.
Vào https://github.com/LamsonRetail/lsr-agent-platform/pull/32 xem check có xanh không.

---

## Vùng cấm — scope-guard sẽ chặn

Chỉ được sửa:

- ✅ `agents/AG-INVENTORY-DAYS/**`
- ✅ `apps/agents/AG-INVENTORY-DAYS/**`

Đụng vào là PR đỏ (`meitheoo` không nằm trong `.github/maintainers.txt`):

- ❌ `.github/` · `infra/` · `src/` (gốc repo) · `scripts/` · `plugins/` · `tests/` · `docs/`
- ❌ `agents/AG-LSR-BRAIN/` · `agents/minh-anh/` (agent nền tảng)

**Cần sửa vùng cấm?** Để bản gốc trong `agents/AG-INVENTORY-DAYS/deploy/`, rồi nhờ
maintainer (`ntranthi` hoặc `thienquy71`) chép ra. Đừng tìm cách lách.

---

## Thêm code mới thì nhớ

`agent-gate` bắt buộc agent có file `.py` thì phải có **`USECASE.md`** và
**`TESTCASES.md`**. Hai file đã có sẵn — thêm tính năng thì **cập nhật chúng**,
đừng để lệch với code.

Nguyên tắc của platform: **use case → test case → code**, đúng thứ tự đó.

---

## Checklist trước khi push

- [ ] Bot đã dừng
- [ ] `python ../tests/test_coc.py` xanh hết
- [ ] Có tính năng mới → đã cập nhật `USECASE.md` + `TESTCASES.md`
- [ ] Không đụng file ngoài `agents/AG-INVENTORY-DAYS/`
- [ ] Đã sửa message commit trong `push_to_github.bat`
- [ ] Không có secret trong code (app_secret chỉ nằm ở `.env`, đã gitignore)

---

## Sau khi push, bật bot lại

`bot_nen_START.vbs` → mở `bot_log.txt`, dòng `Bắt đầu poll` phải in ra **tên nhóm**
(chữ tiếng Việt). Nếu in ra mã `oc_...` là đang bị ghim vào một nhóm — kiểm tra
`CHAT_ID` trong `_bot_loop.bat`, phải để trống.

---

## Ba lỗi đã mất thời gian nhất — đừng lặp lại

| Triệu chứng | Nguyên nhân thật |
|---|---|
| Sửa file rồi mà bot vẫn chạy bản cũ | Chưa tắt bật lại bot. Sửa file **không** tự áp dụng |
| Bot không thấy nhóm mới | `--chat-id` ghim cứng ở **cả hai** đường chạy: `run_bot.bat` (hiện cửa sổ) và `_bot_loop.bat` (chạy nền). Sửa một chỗ là chưa đủ |
| Bot trả lời trùng 2 lần | Hai tiến trình cùng chạy. Đã có khoá `bot.lock`, nhưng vẫn nên STOP trước khi START |

---

## Muốn biết bot đang sống hay chết

Mở `bot_log.txt`, xem dòng cuối:

| Thấy gì | Nghĩa là |
|---|---|
| `Bắt đầu poll ... — N nhóm: <tên>` | Đang chạy bình thường |
| `Câu hỏi: ...` rồi `Đã trả lời.` | Có người hỏi và bot đã đáp |
| `Đã có một bản bot đang chạy` | Bản thứ hai tự thoát — đúng, không phải lỗi |
| `Lỗi mạng: ConnectionError` | Mất mạng, bot tự chờ rồi thử lại |
| `da dung theo yeu cau` | Đã dừng hẳn |
| Không có dòng mới sau khi bật | Bot **chưa** chạy — chạy `run_bot.bat` để thấy lỗi thật |
