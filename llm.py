"""
Profit Lens — LLM Routing Layer
Mattingly AI & Operations Hackathon 2026

Hybrid model architecture:
  GROQ (llama-3.3-70b-versatile)        → conversational chatbot + mini Q&A
  NVIDIA Nemotron (nemotron-super-49b)   → structured operational outputs:
                                            - AI Suggested Next Action cards
                                            - Ticket enhancement (ROOT CAUSE / NEXT STEP)
                                            - Notifications situational brief

Philosophy:
  - LLMs NEVER generate or modify financial numbers.
  - All figures come from the Python engine via _HF dict.
  - LLMs only turn pre-computed numbers + live ticket state into clear guidance.
  - Graceful degradation: NVIDIA unavailable → Groq; both unavailable → static.
"""

import os
import re

# ── Model identifiers ──────────────────────────────────────────────────────────
GROQ_MODEL     = "llama-3.3-70b-versatile"
NEMOTRON_MODEL = "nvidia/nemotron-super-49b-v1"   # best available on NIM free tier
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

# ── Key availability flags (set after loading) ────────────────────────────────
GROQ_API_KEY   = ""
NVIDIA_API_KEY = ""

_GROQ_AVAILABLE   = False
_NVIDIA_AVAILABLE = False


# ── Key loaders ───────────────────────────────────────────────────────────────
def _load_secrets_toml_key(key_name: str) -> str:
    """Read a key directly from .streamlit/secrets.toml (local dev fallback)."""
    try:
        secrets_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), ".streamlit", "secrets.toml"
        )
        if os.path.exists(secrets_path):
            m = re.search(
                rf'{key_name}\s*=\s*["\'](.+?)["\']',
                open(secrets_path).read()
            )
            if m:
                return m.group(1)
    except Exception:
        pass
    return ""


def _load_groq_key() -> str:
    """3-layer Groq key loader: env var → Streamlit secrets → secrets.toml."""
    key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        try:
            import streamlit as st
            key = st.secrets["GROQ_API_KEY"]
        except Exception:
            pass
    if not key:
        key = _load_secrets_toml_key("GROQ_API_KEY")
    return key


def _load_nvidia_key() -> str:
    """3-layer NVIDIA key loader: env var → Streamlit secrets → secrets.toml."""
    key = os.environ.get("NVIDIA_API_KEY", "")
    if not key:
        try:
            import streamlit as st
            key = st.secrets["NVIDIA_API_KEY"]
        except Exception:
            pass
    if not key:
        key = _load_secrets_toml_key("NVIDIA_API_KEY")
    return key


def init_keys():
    """
    Load all API keys and set availability flags.
    Call once at app startup (before set_page_config in app.py).
    Returns (groq_key, nvidia_key, groq_available, nvidia_available).
    """
    global GROQ_API_KEY, NVIDIA_API_KEY, _GROQ_AVAILABLE, _NVIDIA_AVAILABLE

    GROQ_API_KEY = _load_groq_key()
    NVIDIA_API_KEY = _load_nvidia_key()

    try:
        from groq import Groq as _Groq  # noqa: F401
        _GROQ_AVAILABLE = bool(GROQ_API_KEY)
    except ImportError:
        _GROQ_AVAILABLE = False

    try:
        from openai import OpenAI as _OpenAI  # noqa: F401
        _NVIDIA_AVAILABLE = bool(NVIDIA_API_KEY)
    except ImportError:
        _NVIDIA_AVAILABLE = False

    return GROQ_API_KEY, NVIDIA_API_KEY, _GROQ_AVAILABLE, _NVIDIA_AVAILABLE


# ── Core callers ──────────────────────────────────────────────────────────────
def call_nemotron(
    system: str,
    user: str,
    max_tokens: int = 300,
    temperature: float = 0.1,
    reasoning_budget: int = 1024,
) -> str:
    """
    Call NVIDIA Nemotron via the NIM OpenAI-compatible endpoint.

    Uses streaming to handle thinking (reasoning_content) + final answer
    (content) correctly — only the final content is returned.
    reasoning_budget is kept low for structured operational tasks; raise it
    if you need deeper multi-step reasoning.

    Raises RuntimeError if NVIDIA is not available (caller handles fallback).
    """
    if not _NVIDIA_AVAILABLE:
        raise RuntimeError("NVIDIA key not loaded")

    from openai import OpenAI
    client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY)

    stream = client.chat.completions.create(
        model=NEMOTRON_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        extra_body={
            "chat_template_kwargs": {"enable_thinking": True},
            "reasoning_budget": reasoning_budget,
        },
        stream=True,
    )

    content_parts = []
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        # Skip reasoning_content (thinking process) — collect final answer only
        if getattr(delta, "content", None):
            content_parts.append(delta.content)

    return "".join(content_parts).strip()


def call_groq(
    system: str,
    user: str,
    max_tokens: int = 300,
    temperature: float = 0.15,
) -> str:
    """
    Call Groq (LLaMA 3.3 70B) for conversational / creative outputs.

    Raises RuntimeError if Groq is not available (caller handles fallback).
    """
    if not _GROQ_AVAILABLE:
        raise RuntimeError("Groq key not loaded")

    from groq import Groq
    client = Groq(api_key=GROQ_API_KEY)
    resp = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return resp.choices[0].message.content.strip()


def call_structured(system: str, user: str, max_tokens: int = 300) -> str:
    """
    Route for structured operational outputs:
      1. Try Nemotron (precise, low temperature, thinking enabled)
      2. Fall back to Groq (same prompt, slightly higher temperature)
      3. Return empty string if both fail

    This is the single entry point for _ai_next_action, _ai_enhance_ticket,
    and the notifications brief.
    """
    try:
        return call_nemotron(system, user, max_tokens=max_tokens, temperature=0.1)
    except Exception:
        pass
    try:
        return call_groq(system, user, max_tokens=max_tokens, temperature=0.15)
    except Exception:
        pass
    return ""


# ── Status summary (for display in app) ───────────────────────────────────────
def model_status() -> dict:
    """Return display strings for the AI status indicator."""
    return {
        "structured": (
            f"Nemotron ({NEMOTRON_MODEL.split('/')[-1]})"
            if _NVIDIA_AVAILABLE else
            (f"Groq ({GROQ_MODEL})" if _GROQ_AVAILABLE else "Static fallback")
        ),
        "chat": (
            f"Groq ({GROQ_MODEL})" if _GROQ_AVAILABLE else "Offline"
        ),
        "nvidia_live": _NVIDIA_AVAILABLE,
        "groq_live":   _GROQ_AVAILABLE,
    }
