"""Shared chat-message assembly for OpenAI-compatible text providers.

Every text provider (groq / mistral / nvidia / openrouter / mock) takes the same
inputs: an optional system prompt, optional multi-turn history, and the current
user prompt. They all speak the OpenAI "messages" wire format, so the ordering
logic lives here once instead of being copy-pasted six times.

Ordering matters to the model: system first, then history oldest->newest, and
the CURRENT user prompt always last (models weight the final turn most heavily).
"""

from typing import Dict, List, Optional

# Safety cap so a long session can't blow past a provider's context window or
# rack up token cost. ~8 turns is plenty for CS (most threads are 2-4 turns).
MAX_HISTORY_MESSAGES = 12


def build_openai_messages(
    prompt: str,
    system_prompt: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
) -> List[Dict[str, str]]:
    """Assemble [system?, ...history, user] with history sanitised and capped."""
    messages: List[Dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    if history:
        # Keep only well-formed user/assistant turns; drop blanks and anything
        # with an unexpected role (e.g. a stray "system" row from the DB).
        turns = [
            {"role": h["role"], "content": h["content"]}
            for h in history
            if isinstance(h, dict)
            and h.get("role") in ("user", "assistant")
            and isinstance(h.get("content"), str)
            and h["content"].strip()
        ]
        # Cap from the FRONT so the most recent turns always survive.
        if len(turns) > MAX_HISTORY_MESSAGES:
            turns = turns[-MAX_HISTORY_MESSAGES:]
        messages.extend(turns)

    messages.append({"role": "user", "content": prompt})
    return messages
