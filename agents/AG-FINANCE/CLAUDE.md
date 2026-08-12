# Luật làm việc trong dự án AG-FINANCE

File này áp dụng cho mọi phiên Claude Code làm việc trong `agents/AG-FINANCE/`.

## Giới hạn tuyệt đối: chỉ sửa trong thư mục này

Bạn **chỉ** được thêm/sửa/xoá file trong `agents/AG-FINANCE/`.

Không sửa, kể cả khi thấy có bug hoặc thấy cách làm hay hơn:
`infra/` · `src/` · `libs/` · `scripts/` · `plugins/` · `installers/` ·
`apps/platform-web/` · `.github/` · `tests/` (ở gốc repo) · `docs/` (ở gốc repo) ·
`agents/AG-LSR-BRAIN/` · `agents/minh-anh/` · `agents/AG-MINH-ANH/` ·
mọi file `.md`, `pyproject.toml`, `requirements.txt` ở gốc repo.

Đây là CORE của platform. Sửa vào đó sẽ bị `.github/workflows/scope-guard.yml` chặn và
git hook local cũng chặn từ lúc commit.

Nếu việc đang làm **bắt buộc** phải đổi core: dừng lại, nói rõ cần đổi file nào và vì sao,
để người dùng mở issue nhờ maintainer. Đừng tự sửa rồi báo sau.

## Thư mục ai sở hữu cái gì

| Đường dẫn | Người phụ trách | Ghi chú |
|---|---|---|
| `data_hub/` | Hương | Nạp và chuẩn hoá dữ liệu, hỏi đáp số liệu |
| `meeting/` | Thái | Biên bản họp |
| `shared/` | cả hai | Sửa ở đây ảnh hưởng cả hai người → PR phải có review |
| `consumer.py` | cả hai | Chỉ điều phối, giữ mỏng. Logic nghiệp vụ để trong module |
| `USECASE.md`, `TESTCASES.md`, `lsr-agent.yaml`, `system_prompt.md` | chủ dự án | Đổi cần thống nhất trước |

Đang làm việc của Hương thì đừng sửa file trong `meeting/`, và ngược lại. Cần đổi phần của
người kia thì nói ra, đừng tự sửa.

## Quy ước bắt buộc của platform

- **Use case → test case → code.** `USECASE.md` và `TESTCASES.md` phải được cập nhật
  *trước* khi viết code cho luồng mới. CI `agent-gate.yml` chặn nếu thiếu.
- **Không cầm secret.** Không hardcode token, app_secret, API key, email vào code hay
  `lsr-agent.yaml` (manifest nằm trong repo). Tất cả đọc từ biến môi trường, khai trong
  `.env.example` với giá trị giả.
- **Không commit `.env`, không commit dữ liệu tài chính thật.** Không có file CSV/XLSX số
  liệu thật nào được vào git.
- **Gửi tin Lark qua `shared/lark.py`** (bọc `libs/lsr_lark` chế độ remote). Không tự gọi
  Lark API với app_secret.
- **Không giữ lịch sử hội thoại trong bộ nhớ process.** Platform giữ qua
  `/v1/self/context` và `/v1/self/session/turn`.

## Nguyên tắc viết code cho miền tài chính

- Tiền dùng `Decimal`, không dùng `float`. Không bao giờ.
- Không có giá trị mặc định thầm lặng cho dữ liệu tài chính. Thiếu cột → lỗi, không phải `0`.
- Phân biệt rõ "không tìm thấy" và "bằng 0". Trả `None` cho cái đầu.
- Mọi kết quả có số phải mang theo mốc thời gian đồng bộ của dữ liệu.
- Đồng bộ phải idempotent — chạy hai lần không được nhân đôi dữ liệu.
- Kiểm quyền trước khi truy vấn dữ liệu, không phải sau. Mặc định từ chối.

## Khi viết test

Test bám theo ID trong `TESTCASES.md` (A1, B3, D5...). Đặt tên hàm test có ID trong đó để
soi ngược được, ví dụ `test_a1_nguoi_ngoai_squad_bi_tu_choi`.

Không mock tầng dữ liệu bằng số đẹp rồi coi là pass. Case quan trọng nhất là case dữ liệu
xấu: thiếu cột, sai định dạng, nguồn chết, hai nguồn lệch nhau.
