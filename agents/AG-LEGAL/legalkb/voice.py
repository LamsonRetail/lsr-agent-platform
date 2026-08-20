"""Nghe tin nhắn thoại — "Ann nghe được khi gọi tên".

Lark gửi tin thoại dưới dạng `message_type=audio` (hoặc `media`), payload có `file_key`
và `duration`. Tải file thì đã có đường chuẩn: `GET /v1/lark/resource` (broker platform,
không cần app_secret).

Việc còn lại là **chuyển thoại thành text**, và ở đây platform CHƯA có gì: không có
endpoint transcribe/speech nào trong `platform_api` lẫn `collector` (đã kiểm 19/08).
Ba đường khả dĩ, xếp theo mức tuân thủ chuẩn:

1. **Core mở broker transcribe** (`POST /v1/transcribe`) — đúng chuẩn nhất, dùng lại được
   cho mọi agent. Minh Anh đã có Whisper large-v3/CUDA trên VM nên hạ tầng có sẵn rồi,
   chỉ thiếu endpoint. → yêu cầu **C11**.
2. **Lark speech-to-text** (`/open-apis/speech_to_text/v1/speech/file_recognize`, scope
   `speech_to_text:speech`) bằng tenant token của app agent — chạy được ngay nhưng là
   **ngoại lệ thứ ba** cùng loại với C1/C9. Không tự thêm; chờ owner quyết.
3. Dịch vụ ngoài — không chọn: nội dung pháp chế không đưa ra ngoài.

Nguyên tắc ở module này: **không có transcriber thì nói thật**, đừng im lặng. Người gửi
voice mà agent không phản hồi gì sẽ tưởng agent hỏng, hoặc tệ hơn là tưởng đã được nghe.
"""
import os
import urllib.request

AUDIO_TYPES = ("audio", "media")
MAX_SECONDS = int(os.environ.get("VOICE_MAX_SECONDS", "600"))

CANNOT_HEAR = (
    "Mình **chưa nghe được tin nhắn thoại** — phần chuyển thoại thành chữ chưa được bật "
    "cho agent.\n\nBạn gõ lại nội dung giúp mình nhé, hoặc gửi file văn bản. "
    "Mình đã ghi nhận để bộ phận kỹ thuật bật tính năng này."
)
TOO_LONG = ("Tin nhắn thoại dài quá ({sec}s, giới hạn {cap}s) nên mình chưa xử lý được. "
            "Bạn chia ngắn hơn hoặc gõ nội dung chính giúp mình.")


def is_voice(payload):
    """Tin này có phải thoại không. Dựa vào message_type, không đoán theo tên file."""
    return (payload or {}).get("message_type") in AUDIO_TYPES


def transcribe(data, hint_name="voice.opus"):
    """Chuyển bytes audio → text. Trả None khi không có transcriber nào được cấu hình.

    `LSR_TRANSCRIBE_URL` là điểm cắm: khi core mở broker (C11) hoặc ops dựng một service
    nội bộ, chỉ cần đặt env này, không phải sửa code nghiệp vụ.
    """
    url = os.environ.get("LSR_TRANSCRIBE_URL")
    if not url:
        return None
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/octet-stream",
                                          "X-File-Name": hint_name})
    with urllib.request.urlopen(req, timeout=300) as r:
        import json
        out = json.loads(r.read().decode() or "{}")
    return (out.get("text") or "").strip() or None


def hear(pf, job, payload, log=print):
    """Nghe một tin thoại. Trả (text, loi) — đúng một trong hai có giá trị.

    Tách khỏi consumer để test được không cần Lark: chỉ cần fake `pf.lark_resource`.
    """
    sec = int(payload.get("duration") or 0) // 1000 or int(payload.get("duration") or 0)
    if sec and sec > MAX_SECONDS:
        return None, TOO_LONG.format(sec=sec, cap=MAX_SECONDS)
    if not os.environ.get("LSR_TRANSCRIBE_URL"):
        return None, CANNOT_HEAR                 # nói thật thay vì im lặng
    try:
        data = pf.lark_resource(payload.get("message_id") or "",
                                payload.get("file_key") or "",
                                app_id=(job.get("reply_to") or {}).get("app_id") or "")
    except Exception as exc:
        log(f"[voice] tải file lỗi: {exc}")
        return None, "Mình không tải được tin nhắn thoại. Bạn thử gửi lại giúp."
    try:
        text = transcribe(data, payload.get("file_name") or "voice.opus")
    except Exception as exc:
        log(f"[voice] transcribe lỗi: {exc}")
        return None, ("Mình nghe được file nhưng chuyển thành chữ bị lỗi. "
                      "Bạn gõ lại nội dung giúp mình.")
    if not text:
        return None, ("Mình không nhận ra nội dung trong tin thoại (có thể quá ngắn hoặc "
                      "nhiều tiếng ồn). Bạn gõ lại giúp mình nhé.")
    return text, None
