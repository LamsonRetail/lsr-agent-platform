"""Import tài liệu training (do HR cung cấp) → markdown → lưu lại.

Hỗ trợ trực tiếp file text/markdown. File .docx/.pdf: cần bộ chuyển đổi riêng
(có thể dùng skill docx/pdf ở tầng runtime); ở đây nêu rõ và giữ chỗ.
"""

from __future__ import annotations

from pathlib import Path

from .models import TrainingMaterial

_TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".text"}


def to_markdown(path: str | Path) -> str:
    """Đọc file training → chuỗi markdown.

    - .md/.txt: lấy nội dung trực tiếp.
    - khác: chưa hỗ trợ chuyển đổi ở tầng này (raise) — dùng converter runtime.
    """

    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in _TEXT_SUFFIXES:
        text = p.read_text(encoding="utf-8")
        if suffix in {".txt", ".text"}:
            # Bọc thành markdown tối thiểu.
            title = p.stem.replace("_", " ").strip()
            return f"# {title}\n\n{text}"
        return text
    raise ValueError(
        f"Chưa hỗ trợ chuyển '{suffix}' sang markdown ở tầng này "
        "(dùng converter .docx/.pdf ở runtime)."
    )


def import_training_file(
    path: str | Path,
    *,
    material_id: str,
    title: str = "",
    tags: list[str] | None = None,
    provided_by: str = "HR",
    created_at: str = "",
) -> TrainingMaterial:
    """Import 1 file training → :class:`TrainingMaterial` (md_content đã sẵn để lưu)."""

    p = Path(path)
    md = to_markdown(p)
    return TrainingMaterial(
        material_id=material_id,
        title=title or p.stem.replace("_", " ").strip(),
        md_content=md,
        source_file=p.name,
        tags=tags or [],
        provided_by=provided_by,
        created_at=created_at,
    )
