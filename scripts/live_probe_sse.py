"""Live SSE probe for the deployed chat widget.

Usage:
  python scripts/live_probe_sse.py --mall shop_2f3c81cf --label beauty-turn1 \
      --message "지성 피부인데 모공이 넓고 피지가 많아요. 어떤 제품을 써야 할까요?"

Prints one JSON line: ttft_ms, total_ms, chars, cards, text, error.
"""
import argparse
import json
import time
import uuid

import httpx

BASE = "https://chatbot-factory-yqa0.onrender.com"


def probe(mall: str, message: str, session_id: str | None = None) -> dict:
    session_id = session_id or str(uuid.uuid4())
    payload = {
        "session_id": session_id,
        "customer_id": "probe",
        "mall_id": mall,
        "message": message,
    }
    started = time.perf_counter()
    first_token_at = None
    tokens: list[str] = []
    cards: list[dict] = []
    error = None

    with httpx.Client(timeout=httpx.Timeout(120.0, connect=30.0)) as client:
        with client.stream("POST", f"{BASE}/api/chat/stream", json=payload) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                raw = line[len("data: "):].strip()
                if raw == "[DONE]":
                    break
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if "token" in event:
                    if first_token_at is None:
                        first_token_at = time.perf_counter()
                    tokens.append(str(event["token"]))
                elif "replace" in event:
                    tokens = [str(event["replace"])]
                elif "recommended_products" in event:
                    cards = event["recommended_products"] or []
                elif "error" in event:
                    error = event["error"]

    finished = time.perf_counter()
    text = "".join(tokens).strip()
    return {
        "session_id": session_id,
        "ttft_ms": round((first_token_at - started) * 1000) if first_token_at else None,
        "total_ms": round((finished - started) * 1000),
        "chars": len(text),
        "card_count": len(cards),
        "cards": [
            {"title": c.get("title"), "price": c.get("price"), "url": c.get("purchase_url")}
            for c in cards
        ],
        "error": error,
        "text": text,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mall", default="shop_2f3c81cf")
    parser.add_argument("--session", default=None)
    parser.add_argument("--label", default="")
    parser.add_argument("--message", required=True)
    args = parser.parse_args()

    result = probe(args.mall, args.message, args.session)
    result["label"] = args.label
    print(json.dumps(result, ensure_ascii=False))
