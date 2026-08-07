"""LSR Brain — logic consolidate tri thức từ second brain các team về shared brain.

Nguyên tắc (khớp system prompt của AG-LSR-BRAIN):
- Chỉ ĐỀ XUẤT ứng viên tri thức; con người (reviewer theo domain) mới duyệt.
- Không đưa dữ liệu cá nhân/nhạy cảm vào shared brain.
- Phát hiện mâu thuẫn với shared beliefs → tạo conflict cho agent owner xác nhận.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Từ khoá loại trừ: dữ liệu cá nhân/nhạy cảm không được lên shared brain.
SENSITIVE = ("lương", "salary", "cccd", "cmnd", "số tài khoản", "bank account",
             "đánh giá cá nhân", "kỷ luật", "hợp đồng lao động", "personal")

# Dấu hiệu tri thức dùng chung (quy trình/quy ước/định nghĩa/bài học).
REUSABLE = ("quy trình", "quy ước", "nguyên tắc", "định nghĩa", "bài học",
            "cách làm", "checklist", "tiêu chuẩn", "công thức", "sop")


@dataclass
class Candidate:
    """Ứng viên tri thức nộp lên chờ review."""

    title: str
    md_content: str
    domain: str = ""
    source_team: str = ""
    source_ref: str = ""

    def as_payload(self) -> dict:
        return {
            "title": self.title, "md_content": self.md_content, "domain": self.domain,
            "source_team": self.source_team, "source_ref": self.source_ref,
        }


@dataclass
class Conflict:
    """Mâu thuẫn giữa brain của team/agent và shared beliefs."""

    team_id: str
    belief_id: str
    agent_claim: str
    shared_claim: str
    agent_id: str = ""
    owner_email: str = ""

    def as_payload(self) -> dict:
        return {
            "team_id": self.team_id, "belief_id": self.belief_id,
            "agent_claim": self.agent_claim, "shared_claim": self.shared_claim,
            "agent_id": self.agent_id, "owner_email": self.owner_email,
        }


@dataclass
class ConsolidationResult:
    candidates: list[Candidate] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)
    skipped_sensitive: int = 0


def is_sensitive(text: str) -> bool:
    low = (text or "").lower()
    return any(k in low for k in SENSITIVE)


def is_reusable(text: str) -> bool:
    low = (text or "").lower()
    return any(k in low for k in REUSABLE)


def _norm(s: str) -> set[str]:
    return {w for w in re.findall(r"[0-9a-zà-ỹ]+", (s or "").lower()) if len(w) > 3}


def detect_conflict(claim: str, belief_statement: str, *, threshold: float = 0.34) -> bool:
    """Mâu thuẫn thô: cùng chủ đề (đủ từ chung) nhưng một bên phủ định bên kia.

    Heuristic cho giai đoạn đầu; giai đoạn sau thay bằng LLM judge.
    """

    a, b = _norm(claim), _norm(belief_statement)
    if not a or not b:
        return False
    overlap = len(a & b) / min(len(a), len(b))
    if overlap < threshold:
        return False  # khác chủ đề → không phải mâu thuẫn
    neg = ("không", "chưa", "cấm", "tuyệt đối không", "ngưng", "bỏ")
    a_neg = any(n in (claim or "").lower() for n in neg)
    b_neg = any(n in (belief_statement or "").lower() for n in neg)
    return a_neg != b_neg  # một bên phủ định, bên kia không → xung đột


def consolidate_team(
    team_id: str,
    context_entries: list[dict],
    beliefs: list[dict],
    *,
    agent_id: str = "",
    owner_email: str = "",
) -> ConsolidationResult:
    """Chắt lọc context của một team → ứng viên tri thức + phát hiện mâu thuẫn."""

    res = ConsolidationResult()
    for entry in context_entries or []:
        title = (entry.get("title") or "").strip()
        body = (entry.get("md_content") or "").strip()
        if not body:
            continue
        blob = f"{title}\n{body}"
        if is_sensitive(blob):
            res.skipped_sensitive += 1
            continue
        if is_reusable(blob):
            res.candidates.append(Candidate(
                title=title or body[:60],
                md_content=body,
                domain=(entry.get("tags") or [""])[0] if entry.get("tags") else "",
                source_team=team_id,
                source_ref=entry.get("source_ref") or f"team_context:{team_id}",
            ))
        for b in beliefs or []:
            if detect_conflict(body, b.get("statement", "")):
                res.conflicts.append(Conflict(
                    team_id=team_id, belief_id=b.get("belief_id", ""),
                    agent_claim=body[:500], shared_claim=b.get("statement", "")[:500],
                    agent_id=agent_id, owner_email=owner_email,
                ))
    return res
