# C14 — Thêm domain `im` cho User Identity Broker (chat dưới danh tính account agent)

> Người yêu cầu: AG-LEGAL (owner `thint@hapas.vn`) · 21/08/2026
> Phụ thuộc: C8 (đã xong)

## Một câu

Xin thêm `"im"` vào `_LARK_USER_SCOPES` của C8, để agent **nhận và trả lời tin nhắn dưới
danh tính account máy của nó** (`ann_legal@hapas.vn`) — không chỉ đọc Approval.

## Vì sao owner cần

Trong group, `ann_legal@hapas.vn` hiện lên như **một người tên "Ann Nguyen"**. Nhân viên
nhắn cho Ann là chuyện tự nhiên nhất, và họ đã làm — nhưng **không có phản hồi**, vì Ann là
user account không có quyền `im:*`, còn agent thì nói chuyện qua bot của app. Owner muốn:
"tất cả mọi người nhắn với user account thì được trả lời, đầy đủ tính năng".

## Xin gì

```python
_LARK_USER_SCOPES = {
    "approval": [...],
    "im": ["im:message", "im:message:send_as_user", "im:chat:readonly"],   # ← thêm
}
```

Rồi admin cấp lại cho `ann_legal@hapas.vn` với `domains: "approval,im"` và mở
`path_prefixes: ["/open-apis/approval/v4/", "/open-apis/im/v1/"]`.

Tên scope **phải lấy từ user token đang chạy thật** trong tenant (`lark-cli auth status`),
không đoán — đúng bài học đã ghi ở `docs/LARK_USER_BROKER.md` (đoán `approval:instance:readonly`
thì nhận `invalid_scope`).

## ⚠️ Hạn chế kỹ thuật phải biết TRƯỚC khi làm

**Lark không đẩy event cho user account.** Long-connection / webhook là cơ chế **cấp app**,
event `im.message.receive_v1` giao cho **bot**. Một account người không có kênh event.

Hệ quả: dù có scope `im`, agent **không "nhận" được tin của Ann theo thời gian thực** — nó
phải **POLL**: liệt kê chat của Ann rồi đọc tin mới từng chat. Nghĩa là:

| | Qua **bot** (đang có) | Qua **user account** (nếu làm C14) |
|---|---|---|
| Cơ chế | event, tức thời | **poll**, trễ theo chu kỳ |
| Quota Lark | 1 event/tin | N lời gọi/chu kỳ × số chat |
| Log Lark | phân biệt được người/máy | tin do "một người" gửi |
| Cần core làm | không (chỉ bật event trong app) | C14 + cấp lại quyền |

Điểm cuối đáng cân nhắc nhất: `docs/LARK_USER_BROKER.md` §"Chính sách" ghi rõ mục đích của
account riêng là **"để log Lark phân biệt được người và máy"**. Cho agent chat dưới danh
tính đó làm mờ đúng ranh giới ấy — nên nếu làm, đề nghị buộc kèm điều kiện: agent luôn mở
đầu hội thoại bằng một câu nói rõ đây là máy.

## Cách rẻ hơn cho cùng mục tiêu (đề nghị làm trước)

Đổi **tên bot** của app AG-LEGAL thành "Ann", và đổi tên user account thành thứ rõ là nội
bộ (vd "AG-LEGAL Approval"). Khi đó "nhắn Ann" tìm tới **bot** — tức tới agent — với event
tức thời, không cần C14, không cần đổi core. Việc này là **một thao tác trên Lark Developer
Console**, không phải việc của core.

C14 vẫn nên làm nếu sau này có agent cần hành động trong chat dưới danh tính account riêng
(vd đại diện một bộ phận), nhưng không phải đường ngắn nhất cho việc trước mắt.
