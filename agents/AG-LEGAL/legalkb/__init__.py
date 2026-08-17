"""legalkb — kho tri thức pháp chế của AG-LEGAL.

Các mảnh ghép:
- lark_client: đọc Lark Wiki/Drive bằng tenant token (stdlib, theo pattern libs/lsr_lark)
- store:       SQLite ánh xạ tài liệu Lark ↔ source NotebookLM (legal_sources)
- engine:      AnswerEngine interface + NotebookLMEngine (notebooklm-py, unofficial)
- sync:        đồng bộ Wiki/Drive → notebook, phát hiện thêm/sửa/xoá
"""
