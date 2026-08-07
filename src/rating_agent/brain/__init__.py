"""LSR Brain — consolidate tri thức từ second brain các team về shared brain."""

from .consolidate import (
    Candidate,
    Conflict,
    ConsolidationResult,
    consolidate_team,
    detect_conflict,
    is_reusable,
    is_sensitive,
)

__all__ = [
    "Candidate", "Conflict", "ConsolidationResult",
    "consolidate_team", "detect_conflict", "is_reusable", "is_sensitive",
]
