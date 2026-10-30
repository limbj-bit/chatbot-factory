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


DEFAULT_TEASER = {
    "first_delay_ms": 12000,
    "visible_ms": 4500,
    "gap_ms": 32000,
    "max_shows": 4,
}
_DEFAULT_TEASER = DEFAULT_TEASER  # back-compat alias


def read_teaser(
    policy: Optional[Dict[str, Any]],
    *,
    industry: str = "general",
    bot_name: str = "상담봇",
) -> Dict[str, Any]:
    """Closed-chat launcher teaser popups (not in-chat welcome bubbles)."""
    from app.domain.teaser_prompts import get_teaser_prompts

    raw = (policy or {}).get("teaser") if isinstance(policy, dict) else None
    raw = raw if isinstance(raw, dict) else {}
    prompts = raw.get("prompts")
    if not isinstance(prompts, list) or not [p for p in prompts if str(p).strip()]:
        prompts = get_teaser_prompts(industry, bot_name)
    else:
        prompts = [str(p).strip() for p in prompts if str(p).strip()][:12]

    def _ms(key: str, default: int, hi: int) -> int:
        try:
            v = int(raw.get(key, default))
        except Exception:
            v = default
        return max(0, min(v, hi))

    return {
        "prompts": prompts,
        "first_delay_ms": _ms("first_delay_ms", _DEFAULT_TEASER["first_delay_ms"], 120000),
        "visible_ms": _ms("visible_ms", _DEFAULT_TEASER["visible_ms"], 60000),
        "gap_ms": _ms("gap_ms", _DEFAULT_TEASER["gap_ms"], 300000),
        "max_shows": _clamp_max_shows(raw.get("max_shows")),
    }


def _clamp_max_shows(val: Any) -> int:
    try:
        n = int(val) if val is not None else _DEFAULT_TEASER["max_shows"]
    except Exception:
        n = _DEFAULT_TEASER["max_shows"]
    return max(1, min(n, 20))


def merge_teaser_into_policy(
    policy: Dict[str, Any],
    *,
    prompts: Optional[List[str]] = None,
    first_delay_ms: Optional[int] = None,
    visible_ms: Optional[int] = None,
    gap_ms: Optional[int] = None,
    max_shows: Optional[int] = None,
) -> Dict[str, Any]:
    out = dict(policy or {})
    cur = read_teaser(out, industry="general", bot_name="상담봇")
    # If prompts omitted, keep existing custom or empty list marker
    if prompts is not None:
        cur["prompts"] = [str(p).strip() for p in prompts if str(p).strip()][:12]
    if first_delay_ms is not None:
        cur["first_delay_ms"] = max(0, min(int(first_delay_ms), 120000))
    if visible_ms is not None:
        cur["visible_ms"] = max(0, min(int(visible_ms), 60000))
    if gap_ms is not None:
        cur["gap_ms"] = max(0, min(int(gap_ms), 300000))
    if max_shows is not None:
        cur["max_shows"] = max(1, min(int(max_shows), 20))
    out["teaser"] = {
        "prompts": cur["prompts"],
        "first_delay_ms": cur["first_delay_ms"],
        "visible_ms": cur["visible_ms"],
        "gap_ms": cur["gap_ms"],
        "max_shows": cur["max_shows"],
    }
    return out
