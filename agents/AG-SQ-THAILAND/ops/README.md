# Vận hành Ploy — giữ bot KHÔNG bị tắt

> Vì sao cần: 19/08 trong nhóm sharing có tin Ploy trả lời **sau ~1,5 tiếng** kèm nhận xét
> *"ô em tắt rồi mà tự nhiên xuất hiện"*. Nguyên nhân không phải model chậm — mà là
> **consumer bị tắt** (đang chạy trên máy cá nhân), tin nằm chờ trong hàng đợi của
> platform tới khi bot bật lại. Job không mất, nhưng người hỏi thì đã đi mất.

## Cách đúng (đích đến): container trên VM

Chạy cạnh gateway trên VM platform — nhờ admin (Dockerfile + docker-compose.yml đã có
sẵn trong thư mục agent). Đây là bản duy nhất **không phụ thuộc máy cá nhân**.

## Cách tạm trên máy macOS (khi chưa lên VM)

```bash
# 1. Cài launchd agent — tự bật lại khi crash, tự chạy sau khi đăng nhập máy
cp "agents/AG-SQ-THAILAND/ops/com.lsr.ploy.plist" ~/Library/LaunchAgents/
launchctl load -w ~/Library/LaunchAgents/com.lsr.ploy.plist

# 2. Kiểm tra đang chạy (cột đầu = PID, khác '-' là sống)
launchctl list | grep com.lsr.ploy

# 3. Xem log
tail -f ~/Library/Logs/ploy.log

# 4. Nạp lại sau khi sửa code / sửa .env
launchctl kickstart -k gui/$(id -u)/com.lsr.ploy

# 5. Tắt hẳn
launchctl unload ~/Library/LaunchAgents/com.lsr.ploy.plist
```

**Hạn chế phải biết:** máy **tắt / ngủ / mất mạng** thì bot vẫn dừng — launchd chỉ chống
crash và chống đóng terminal. Muốn 24/7 thì phải lên VM. Nếu máy hay ngủ, tắt sleep khi
cắm điện: System Settings → Lock Screen / Battery → "Prevent automatic sleeping".

## Bot tự thú nhận khi trả lời trễ

`consumer.py` đánh dấu: job nhận trong 90 giây đầu sau khi bật = job đã nằm chờ → Ploy
thêm dòng *"(Em vừa được bật lại nên trả lời trễ — tin của anh/chị nằm trong hàng đợi.
Không mất tin nào ạ.)"*. Trung thực hơn là im lặng xuất hiện sau nhiều giờ.

## Kiểm tra sức khoẻ nhanh

```bash
# bot có đang chạy?
pgrep -fl "consumer.py"

# platform còn sống? (200 = ok)
curl -sk -o /dev/null -w '%{http_code}\n' https://platform.34-126-154-135.sslip.io/health

# chạy bộ test không cần mạng
python3 tests/run_offline.py && python3 tests/selfcheck_flows.py
```

Log có dòng `poll 502` / `poll 401` liên tục = platform đang restart hoặc token bị thu
hồi. Chờ vài phút rồi `launchctl kickstart -k gui/$(id -u)/com.lsr.ploy`; nếu vẫn 401 thì
hỏi admin cấp lại `LSR_AGENT_TOKEN`.
