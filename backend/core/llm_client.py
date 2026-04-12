"""
Unified LLM client — abstracts OpenAI vs Anthropic.

Usage:
    from backend.core.llm_client import llm_complete, llm_structured

    # Non-streaming
    text = llm_complete(messages=[{"role":"user","content":"..."}], system="...", model_key="main")

    # Streaming (returns a generator of str chunks)
    for chunk in llm_complete(..., stream=True):
        print(chunk, end="")

    # Structured output (returns a Pydantic model instance)
    result = llm_structured(messages=[...], system="...", model_key="fast", schema=MySchema)

model_key:
    "main"  → gpt-4o  / claude-sonnet-4-6
    "fast"  → gpt-4o-mini / claude-haiku-4-5
"""
from __future__ import annotations

import json
import re
from typing import Generator, Type, Union

from pydantic import BaseModel

from backend.core.config import (
    LLM_PROVIDER,
    OPENAI_API_KEY,
    LLM_MODEL,
    RERANK_MODEL,
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    ANTHROPIC_RERANK_MODEL,
    GOOGLE_API_KEY,
    GEMINI_MODEL,
    GEMINI_RERANK_MODEL,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _openai_model(model_key: str) -> str:
    return LLM_MODEL if model_key == "main" else RERANK_MODEL


def _anthropic_model(model_key: str) -> str:
    return ANTHROPIC_MODEL if model_key == "main" else ANTHROPIC_RERANK_MODEL


def _gemini_model(model_key: str) -> str:
    return GEMINI_MODEL if model_key == "main" else GEMINI_RERANK_MODEL


def _extract_json(text: str) -> str:
    """Extract first JSON object or array from text (handles markdown code fences)."""
    # Strip ```json ... ``` fences
    fenced = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if fenced:
        return fenced.group(1)
    # Grab first { ... } block
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        return m.group(0)
    return text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def llm_complete(
    messages: list[dict],
    system: str = "",
    model_key: str = "main",
    max_tokens: int = 2000,
    stream: bool = False,
) -> Union[str, Generator[str, None, None]]:
    """
    Call the configured LLM provider.

    Args:
        messages:   List of {"role": ..., "content": ...} dicts (no system message).
        system:     System prompt string (kept separate for Anthropic compatibility).
        model_key:  "main" for primary model, "fast" for cheaper/faster model.
        max_tokens: Maximum tokens to generate.
        stream:     If True, returns a generator yielding str chunks.

    Returns:
        str if stream=False, Generator[str] if stream=True.
    """
    if LLM_PROVIDER == "anthropic":
        return _anthropic_complete(messages, system, model_key, max_tokens, stream)
    elif LLM_PROVIDER == "gemini":
        return _gemini_complete(messages, system, model_key, max_tokens, stream)
    else:
        return _openai_complete(messages, system, model_key, max_tokens, stream)


def llm_structured(
    messages: list[dict],
    system: str = "",
    model_key: str = "main",
    schema: Type[BaseModel] = None,
    max_tokens: int = 2000,
) -> BaseModel | None:
    """
    Call the configured LLM and return a validated Pydantic model instance.

    OpenAI:    Uses beta.chat.completions.parse() with response_format=schema.
    Anthropic: Injects JSON instructions, parses response manually.

    Returns None on failure.
    """
    if LLM_PROVIDER == "anthropic":
        return _anthropic_structured(messages, system, model_key, schema, max_tokens)
    elif LLM_PROVIDER == "gemini":
        return _gemini_structured(messages, system, model_key, schema, max_tokens)
    else:
        return _openai_structured(messages, system, model_key, schema, max_tokens)


# ---------------------------------------------------------------------------
# OpenAI implementation
# ---------------------------------------------------------------------------

def _openai_complete(messages, system, model_key, max_tokens, stream):
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    model = _openai_model(model_key)

    # Build full message list with system prepended if provided
    full_messages = []
    if system:
        full_messages.append({"role": "system", "content": system})
    full_messages.extend(messages)

    if stream:
        def _gen():
            resp = client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                messages=full_messages,
                stream=True,
            )
            for chunk in resp:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        return _gen()
    else:
        resp = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=full_messages,
        )
        return resp.choices[0].message.content or ""


def _openai_structured(messages, system, model_key, schema, max_tokens):
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    model = _openai_model(model_key)

    full_messages = []
    if system:
        full_messages.append({"role": "system", "content": system})
    full_messages.extend(messages)

    try:
        resp = client.beta.chat.completions.parse(
            model=model,
            max_tokens=max_tokens,
            messages=full_messages,
            response_format=schema,
        )
        return resp.choices[0].message.parsed
    except Exception:
        # Fallback: plain completion + manual JSON parse
        try:
            text = _openai_complete(messages, system, model_key, max_tokens, stream=False)
            data = json.loads(_extract_json(text))
            return schema(**data) if schema else data
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Anthropic implementation
# ---------------------------------------------------------------------------

def _anthropic_complete(messages, system, model_key, max_tokens, stream):
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    model = _anthropic_model(model_key)

    kwargs = dict(model=model, max_tokens=max_tokens, messages=messages)
    if system:
        kwargs["system"] = system

    if stream:
        def _gen():
            with client.messages.stream(**kwargs) as s:
                for text in s.text_stream:
                    yield text
        return _gen()
    else:
        resp = client.messages.create(**kwargs)
        return resp.content[0].text if resp.content else ""


def _anthropic_structured(messages, system, model_key, schema, max_tokens):
    """
    Anthropic has no native structured-output API.
    We inject JSON instructions into the system prompt and parse the response.
    """
    import anthropic

    schema_desc = ""
    if schema:
        try:
            schema_desc = json.dumps(schema.model_json_schema(), indent=2)
        except Exception:
            schema_desc = str(schema)

    json_instruction = (
        "\n\nIMPORTANT: You must respond with ONLY valid JSON that exactly matches "
        "this schema — no markdown, no explanation, no extra text:\n" + schema_desc
    )
    augmented_system = (system or "") + json_instruction

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    model = _anthropic_model(model_key)

    kwargs = dict(model=model, max_tokens=max_tokens, messages=messages, system=augmented_system)
    try:
        resp = client.messages.create(**kwargs)
        raw = resp.content[0].text if resp.content else ""
        data = json.loads(_extract_json(raw))
        return schema(**data) if schema else data
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Gemini implementation
# ---------------------------------------------------------------------------

def _gemini_messages_to_contents(messages: list[dict]) -> list[dict]:
    """Convert OpenAI-style messages to Gemini 'contents' format."""
    contents = []
    for msg in messages:
        role = msg.get("role", "user")
        # Gemini uses "user" / "model" instead of "user" / "assistant"
        gemini_role = "model" if role == "assistant" else "user"
        contents.append({
            "role": gemini_role,
            "parts": [{"text": msg.get("content", "")}],
        })
    return contents


def _gemini_complete(messages, system, model_key, max_tokens, stream):
    import google.generativeai as genai
    genai.configure(api_key=GOOGLE_API_KEY)
    model_name = _gemini_model(model_key)

    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=system if system else None,
    )
    contents = _gemini_messages_to_contents(messages)
    generation_config = {"max_output_tokens": max_tokens}

    if stream:
        def _gen():
            resp = model.generate_content(
                contents,
                generation_config=generation_config,
                stream=True,
            )
            for chunk in resp:
                if hasattr(chunk, "text") and chunk.text:
                    yield chunk.text
        return _gen()
    else:
        resp = model.generate_content(
            contents,
            generation_config=generation_config,
        )
        return resp.text or ""


def _gemini_structured(messages, system, model_key, schema, max_tokens):
    """Gemini structured output via JSON instruction injection."""
    import google.generativeai as genai

    schema_desc = ""
    if schema:
        try:
            schema_desc = json.dumps(schema.model_json_schema(), indent=2)
        except Exception:
            schema_desc = str(schema)

    json_instruction = (
        "\n\nIMPORTANT: You must respond with ONLY valid JSON that exactly matches "
        "this schema — no markdown, no explanation, no extra text:\n" + schema_desc
    )
    augmented_system = (system or "") + json_instruction

    genai.configure(api_key=GOOGLE_API_KEY)
    model_name = _gemini_model(model_key)
    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=augmented_system,
    )
    contents = _gemini_messages_to_contents(messages)

    try:
        resp = model.generate_content(
            contents,
            generation_config={"max_output_tokens": max_tokens},
        )
        raw = resp.text or ""
        data = json.loads(_extract_json(raw))
        return schema(**data) if schema else data
    except Exception:
        return None
