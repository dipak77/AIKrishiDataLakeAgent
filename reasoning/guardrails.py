"""Query guardrails (V6 DECG Layer A) — input sanitization + injection defence.

Deterministic and offline: no LLM moderation. Strips control characters,
normalizes whitespace, enforces a length cap, and scans a curated list of
prompt-injection / code-execution patterns. A blocked query is *flagged*, not
silently answered, so the gateway can return an empty, marked payload.
"""

from __future__ import annotations

import re
from typing import Any

# Prompt-injection / role-play / template & code-execution patterns. Curated,
# deliberately conservative (flag only, never fabricate).
INJECTION_PATTERNS: list[tuple[str, str]] = [
    (r"ignore\s+(?:all\s+|any\s+)?(?:previous|prior|above|earlier|following)\s+instructions", "instruction_override"),
    (r"(?:system\s*prompt|developer\s*message|system\s*message)", "prompt_leak"),
    (r"role\s*[:=]\s*(?:system|developer)", "role_override"),
    (r"reveal\s+(?:your|the)\s+(?:system\s*)?prompt", "prompt_leak"),
    (r"act\s+as\s+(?:an?\s+)?(?:unrestricted|jailbroken|dan\b)", "jailbreak"),
    (r"pretend\s+to\s+be\s+(?:a|an)?\s*(?:unrestricted|jailbroken)?\s*(?:gpt|assistant|llm|model)", "roleplay"),
    (r"<\|im_start\|>|<\|endoftext\|>|<\|\|.*?\|\|>", "token_marker"),
    (r"</?(?:system|developer|assistant|user|tool|function|function_calls?)\s*>", "tag_injection"),
    (r"\{\{\s*[a-z_][a-z0-9_]*\s*\}\}", "template_injection"),
    (r"\b(?:base64|eval|exec|execfile|__import__|os\.system|subprocess)\b", "code_exec"),
    (r"<script|javascript:", "code_exec"),
]

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WS_RE = re.compile(r"\s+")

MAX_QUERY_LEN = 2000


def sanitize(query: str | None, max_len: int = MAX_QUERY_LEN) -> dict[str, Any]:
    """Return {query, original, blocked, flags, safe} for a raw query string."""
    original = query or ""
    cleaned = _CONTROL_RE.sub("", original)
    cleaned = _WS_RE.sub(" ", cleaned).strip()

    flags: list[str] = []
    for pattern, tag in INJECTION_PATTERNS:
        if re.search(pattern, cleaned, re.IGNORECASE):
            flags.append(tag)
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip()
        flags.append("truncated")
    if cleaned != original:
        flags.append("normalized")

    return {
        "query": cleaned,
        "original": original,
        "blocked": bool(flags and any(f not in ("truncated", "normalized") for f in flags)),
        "flags": flags,
        "safe": not flags or set(flags) <= {"truncated", "normalized"},
    }
