# Minh Anh — Workflow

Meeting agent theo đúng chuẩn platform (đăng ký registry, telemetry bắt buộc, Lark
bot, resource index). Xem [CREATE_AGENT.md](../../CREATE_AGENT.md).

## A. Khi có agent mới register → share từ điển meeting-notes

```
register(agent mới) ──event──► Platform API ──hook on_agent_registered──► Minh Anh
   Minh Anh: share_dictionary_to(index, new_agent_id)
   → tạo 1 resource {folder: meeting-notes, kind: folder, title: "Meeting Notes
     Dictionary"} gắn agent_id = new_agent_id
   → agent mới search folder=meeting-notes là thấy, tra cứu được biên bản cũ
```
Hàm: `rating_agent.meeting.share_dictionary_to(index, new_agent_id)`.
Nguyên tắc: chỉ chia sẻ **chỉ mục**, không đổ nội dung vào memory agent mới.

## B. Khi được add vào cuộc họp → viết biên bản

```
1. Lấy transcript            (Whisper server: POST /transcribe -> poll /result)
2. Trích key_points + decisions
3. Soạn biên bản (draft) + đề xuất task
4. Gửi meeting owner XIN CONFIRM   (Lark IM)      ── status: awaiting_confirm
        │ owner confirm
        ▼
5. Tạo task (Lark Task) + lưu biên bản vào meeting-notes (resource index)
                                                  ── status: confirmed
```
Data model: `MeetingMinutes` (transcript, key_points, decisions, tasks, status).
Không tạo task khi **chưa** có confirm của owner.

## Skills (MCP) dùng
`lark-minutes` (transcript) · `lark-docx` (soạn biên bản) · `lark-task` (tạo task)
· `lark-im` (xin confirm) · `resource-index` (lưu/tra biên bản).

## Transcript — Whisper server
Client: `rating_agent.meeting.TranscribeClient` (submit `/transcribe` → poll
`/result/{job_id}`). Base URL: env `LSR_TRANSCRIBE_URL` (mặc định server ngrok).
Đã ping `/health` từ VM: model `large-v3`, CUDA (GTX 1660 SUPER), sẵn sàng.

## Trạng thái hiện tại
- [x] Logic share dictionary + model biên bản + vòng đời (đã code + test).
- [x] Resource index (collector) đã deploy — biên bản lưu & tra cứu được.
- [x] **Platform API**: register agent → **tự động Minh Anh share từ điển** (live, đã verify).
- [x] Client transcript (Whisper) — đã code + test; server sống.
- [ ] Lark bot runtime: nhận sự kiện add-vào-họp, gửi xin confirm, tạo task (Lark MCP).
