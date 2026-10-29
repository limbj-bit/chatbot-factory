"""Comma-separated model pools with round-robin start + failover."""
from typing import List, Optional


def parse_model_pool(models_csv: Optional[str], single: Optional[str] = None) -> List[str]:
    """Prefer CSV pool; fall back to a single model id for backward compatibility."""
    pool = [m.strip() for m in (models_csv or "").split(",") if m.strip()]
    if pool:
        return pool
    if single and single.strip():
        return [single.strip()]
    return []


def rotate_from(pool: List[str], start_index: int) -> List[str]:
    """Return pool starting at start_index % len, then the rest (for RR + failover)."""
    if not pool:
        return []
    i = start_index % len(pool)
    return pool[i:] + pool[:i]
