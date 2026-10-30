"""First-screen welcome bubbles + timing stored in store.policy_config.first_screen."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def split_welcome_to_bubbles(text: str) -> List[str]:
    """Split legacy welcome_message into editable bubbles (paragraphs)."""
    raw = (text or "").replace("\r\n", "\n").strip()
    if not raw:
        return []
    parts = [p.strip() for p in raw.split("\n\n") if p.strip()]
    return parts if parts else [raw]


def join_bubbles(bubbles: List[str]) -> str:
    cleaned = [b.strip() for b in bubbles if (b or "").strip()]
    return "\n\n".join(cleaned)


def read_first_screen(policy: Optional[Dict[str, Any]], welcome_message: str = "") -> Dict[str, Any]:
    fs = (policy or {}).get("first_screen") if isinstance(policy, dict) else None
    fs = fs if isinstance(fs, dict) else {}
    bubbles = fs.get("bubbles")
    if not isinstance(bubbles, list) or not bubbles:
        bubbles = split_welcome_to_bubbles(welcome_message)
    else:
        bubbles = [str(b).strip() for b in bubbles if str(b).strip()]
    first_delay = int(fs.get("first_delay_ms") or 0)
    gap = int(fs.get("bubble_gap_ms") or 450)
    first_delay = max(0, min(first_delay, 10000))
    gap = max(0, min(gap, 10000))
    return {
        "bubbles": bubbles,
        "first_delay_ms": first_delay,
        "bubble_gap_ms": gap,
    }


def merge_first_screen_into_policy(
    policy: Dict[str, Any],
    *,
    bubbles: Optional[List[str]] = None,
    first_delay_ms: Optional[int] = None,
    bubble_gap_ms: Optional[int] = None,
) -> Tuple[Dict[str, Any], str]:
    """Update policy['first_screen']; return (policy, joined welcome_message)."""
    out = dict(policy or {})
    cur = read_first_screen(out, "")
    if bubbles is not None:
        cur["bubbles"] = [str(b).strip() for b in bubbles if str(b).strip()][:12]
    if first_delay_ms is not None:
        cur["first_delay_ms"] = max(0, min(int(first_delay_ms), 10000))
    if bubble_gap_ms is not None:
        cur["bubble_gap_ms"] = max(0, min(int(bubble_gap_ms), 10000))
    out["first_screen"] = {
        "bubbles": cur["bubbles"],
        "first_delay_ms": cur["first_delay_ms"],
        "bubble_gap_ms": cur["bubble_gap_ms"],
    }
    return out, join_bubbles(cur["bubbles"])
