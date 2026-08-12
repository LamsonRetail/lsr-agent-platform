# Onboarding — dự án AG-FINANCE

Đọc file này trước khi làm gì. Mất khoảng 10 phút.

## Dự án này là gì

Một trợ lý cho squad Finance-Accounting, làm hai việc: tổng hợp số liệu tài chính về một
Lark Base chung để ai trong squad cũng tra được, và dựng biên bản họp.

Chi tiết nghiệp vụ: đọc [USECASE.md](USECASE.md). Danh sách việc cần làm cho chạy đúng:
[TESTCASES.md](TESTCASES.md).

## Điều quan trọng nhất: chỉ sửa trong thư mục này

Repo `lsr-agent-platform` là **platform dùng chung của cả công ty**. Nhiều agent khác đang
chạy trên đó. Dự án của chúng ta là *một thư mục con*:

```
agents/AG-FINANCE/      ← toàn bộ việc của chúng ta nằm ở đây
```

Mọi thứ khác trong repo là core của platform. **Không sửa**, kể cả thấy có lỗi. Có ba lớp
chặn tự động (git hook lúc commit, CI lúc mở PR, và branch protection) nên nếu lỡ chạm ra
ngoài thì sẽ bị báo lỗi ngay — đó là chủ ý, không phải máy hỏng.

Cần đổi core thật sự? Nhắn chủ dự án, không tự sửa.

## Ai làm phần nào

| Người | Thư mục | Nội dung |
|---|---|---|
| **Hương** | `data_hub/` | Nạp dữ liệu từ Google Sheet, MISA AMIS, Lark Base → chuẩn hoá → ghi Lark Base FIN-HUB. Trả lời câu hỏi số liệu. |
| **Thái** | `meeting/` | Nhận recording từ nhóm Lark → transcript → biên bản → xin chốt → tạo task. |
| cả hai | `shared/` | Phân quyền, gửi tin Lark, gọi model. Sửa ở đây phải nói cho người kia biết. |

Hai thư mục `data_hub/` và `meeting/` không dùng chung file nào, nên hai người làm song song
gần như không bao giờ bị trùng.

## Cài đặt (một lần)

```bash
git clone https://github.com/LamsonRetail/lsr-agent-platform.git
cd lsr-agent-platform
git checkout feat/ag-finance
bash agents/AG-FINANCE/scripts/setup-dev.sh
```

Script trên cài git hook chặn ra ngoài phạm vi, tạo virtualenv, và tạo file `.env`. Sau đó
mở `agents/AG-FINANCE/.env` điền token (xin chủ dự án).

Kiểm tra đã ổn:

```bash
cd agents/AG-FINANCE
.venv/bin/python -m pytest tests/ -q
```

## Quy trình làm việc hằng ngày

```bash
# 1. Lấy code mới nhất
git checkout feat/ag-finance && git pull

# 2. Tạo branch riêng cho việc đang làm
git checkout -b fin/huong-doc-google-sheet      # Hương: fin/huong-<việc>
                                                 # Thái:  fin/thai-<việc>
# 3. Sửa code (chỉ trong agents/AG-FINANCE/)

# 4. Chạy test
cd agents/AG-FINANCE && .venv/bin/python -m pytest tests/ -q && cd -

# 5. Commit — hook sẽ tự kiểm phạm vi
git add agents/AG-FINANCE
git commit -m "feat(data_hub): đọc công nợ từ Google Sheet"

# 6. Push và mở PR về feat/ag-finance
git push -u origin fin/huong-doc-google-sheet
```

Đừng push trực tiếp vào `feat/ag-finance` hay `main`. Luôn mở PR để người kia xem qua.

**Thứ tự bắt buộc: use case → test case → code.** Làm một luồng mới thì cập nhật
`USECASE.md` và `TESTCASES.md` trước, rồi mới viết code. CI của platform sẽ chặn nếu ngược
thứ tự.

## Luật riêng của miền tài chính

Đây là dữ liệu công nợ và lãi lỗ thật. Bốn điều không được vi phạm:

1. **Không bao giờ commit số liệu thật** vào git. Không CSV, không XLSX, không screenshot có
   số. Test dùng dữ liệu giả.
2. **Không hardcode token, API key, email** vào code. Đọc từ biến môi trường, khai giá trị
   giả trong `.env.example`.
3. **Tiền dùng `Decimal`, không dùng `float`.** `0.1 + 0.2` trong float không bằng `0.3`, và
   sai số đó sẽ đi vào báo cáo.
4. **Không bịa số.** Thiếu dữ liệu thì trả `None` và nói không có. Không trả `0`. Một con số
   sai còn tệ hơn câu trả lời "tôi không biết".

## Vướng thì làm gì

| Tình huống | Cách xử lý |
|---|---|
| Commit bị hook chặn | Đọc thông báo — có file ngoài `agents/AG-FINANCE/`. Bỏ file đó ra: `git restore --staged <file>` |
| CI báo trượt `scope-guard` | Cùng lý do trên, nhưng phát hiện muộn hơn. Bỏ file ngoài scope rồi push lại |
| CI báo trượt `agent-gate` | Có code mới nhưng `USECASE.md`/`TESTCASES.md` chưa cập nhật |
| Cần đổi file trong core | Nhắn chủ dự án, đừng tự sửa |
| Cần đổi file phần người kia | Nhắn người đó, đừng tự sửa |
| Thiếu token / quyền truy cập nguồn dữ liệu | Nhắn chủ dự án — đang có 5 thứ phải xin, xem bảng trong `USECASE.md` |

## Đọc thêm

- [CLAUDE.md](CLAUDE.md) — luật cho Claude Code, nếu dùng Claude Code làm việc trong repo này
- [docs/DATA_MODEL.md](docs/DATA_MODEL.md) — schema dữ liệu chung
- `../../CONTRIBUTING.md` — quy ước chung của platform
