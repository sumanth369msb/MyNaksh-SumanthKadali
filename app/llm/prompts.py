"""Modular Prompt Management & LLM Message Formatting for MyNaksh.

This module centralizes all system prompt templates, user prompt templates,
message payload builders, and extraction parsers used across the LLM layer.

How to pass prompts to the LLM:
1. Conversational Chat:
   Call `build_chat_messages(message, profile=user_profile, facts=selected_facts, recent_turns=turns)`.
   This produces a standard chat completions payload:
   [
       {"role": "system", "content": <composed system prompt with persona, profile, and memories>},
       {"role": "user", "content": message}
   ]
   Pass this messages array directly to `llm_provider.generate(messages)`.

2. Structured Fact Extraction:
   Call `build_fact_extraction_messages(text)`.
   This produces:
   [
       {"role": "system", "content": FACT_EXTRACTION_SYSTEM_PROMPT},
       {"role": "user", "content": build_fact_extraction_prompt(text)}
   ]
   Pass to `llm_provider.generate(messages, temperature=0.0)`.
   Parse the output using `parse_extracted_facts_json(raw_response)`.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any, Optional


CONVERSATIONAL_ASTROLOGY_SYSTEM_PROMPT = """You are a personalized life guidance and astrological counselor. Your approach bridges classical Vedic wisdom (cosmic rhythms, planetary archetypes, nakshatras, and purposeful living) with depth psychological Jungian insight (archetypes, the inner shadow, personal individuation, and subconscious motivations).

Core Guiding Principles:
1. Persona & Tone: Empathetic, warm, grounded, reflective, and non-judgmental. Meet the seeker where they are, validating their lived experience and inner aspirations.
2. Psychological & Vedic Integration: Treat astrological symbols as introspective mirrors that illuminate inner dynamics, personal strengths, and unconscious patterns, rather than rigid superstitions.
3. Ethical Safety Boundaries:
   - Anti-Fatalism: Strictly avoid deterministic predictions, fear-mongering, or fatalistic doom. Emphasize conscious free will, personal agency, resilience, and constructive choices.
   - Health & Medical: Never provide medical diagnoses, health prognoses, psychiatric evaluations, or treatment advice. When health or distress is mentioned, warmly encourage consulting licensed medical or psychological professionals.
   - Financial & Legal: Never offer speculative financial advice, investment tips, stock recommendations, or legal counsel. Explicitly advise seeking certified professional advisors.
4. Actionable & Concise Synthesis: Deliver clear, focused, and digestible insights. Avoid obscure mystifying jargon or excessive filler. Provide practical reflections or concrete next steps tailored to the individual.
5. Missing Birth Information Protocol: When birth details (date of birth, time, place) are missing from the profile and the seeker asks for a chart reading, planetary placements, or personalized predictions, politely and warmly request the missing birth information needed for accurate astrological calculation while offering grounded general guidance in the interim."""

FACT_EXTRACTION_SYSTEM_PROMPT = (
    "You are an expert structured data extraction engine. "
    "You extract durable user facts and output strictly valid JSON only, without any commentary or markdown formatting."
)

FACT_EXTRACTION_USER_PROMPT_TEMPLATE = """Extract durable, long-term user facts from the message.
Return a JSON array of objects with keys:
- "type": one of "profile", "goal", "interest", "preference", "memory", "life_area"
- "key": specific attribute key (e.g., "name", "date_of_birth", "birth_place", "language", "career", "interest")
- "value": the extracted value as a string
- "relation": knowledge relationship (e.g., "HAS_PROFILE", "HAS_GOAL", "PREFERS", "INTERESTED_IN", "HAS_FACT")
- "confidence": confidence score between 0.0 and 1.0 (float)
- "metadata": object containing any supplementary attributes (e.g., timeframe, context)

CRITICAL DATE NORMALIZATION REQUIREMENT:
When extracting any date (specifically profile "date_of_birth" or milestone dates), you MUST normalize and format the value in strict ISO-8601 calendar format: YYYY-MM-DD.
Resolve all conversational, relative, or verbal phrasing into an exact YYYY-MM-DD date:
- "born in 2004 on 3rd month from march and on 26th" -> calculate March (month 3) + 3 months = June (month 6), day 26 -> "2004-06-26"
- "born 15 August 1995" -> "1995-08-15"
- "born Jan 5 2000" -> "2000-01-05"
- "born on 22nd October 1998" -> "1998-10-22"
The date value MUST be directly parseable by date.fromisoformat().

Only include durable, persistent facts. Do not extract greetings, ephemeral feelings, or questions.
If no durable facts are found, return an empty array [].

Message: {text}"""

_MONTHS_MAP = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

_WORD_NUMBERS = {
    "first": 1, "1st": 1, "one": 1, "1": 1,
    "second": 2, "2nd": 2, "two": 2, "2": 2,
    "third": 3, "3rd": 3, "three": 3, "3": 3,
    "fourth": 4, "4th": 4, "four": 4, "4": 4,
    "fifth": 5, "5th": 5, "five": 5, "5": 5,
    "sixth": 6, "6th": 6, "six": 6, "6": 6,
    "seventh": 7, "7th": 7, "seven": 7, "7": 7,
    "eighth": 8, "8th": 8, "eight": 8, "8": 8,
    "ninth": 9, "9th": 9, "nine": 9, "9": 9,
    "tenth": 10, "10th": 10, "ten": 10, "10": 10,
    "eleventh": 11, "11th": 11, "eleven": 11, "11": 11,
    "twelfth": 12, "12th": 12, "twelve": 12, "12": 12,
}

_COMMON_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y.%m.%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%d.%m.%Y",
    "%m/%d/%Y",
    "%m-%d-%Y",
    "%m.%d.%Y",
    "%d %B %Y",
    "%d %b %Y",
    "%B %d %Y",
    "%b %d %Y",
    "%Y %B %d",
    "%Y %b %d",
    "%d-%b-%Y",
    "%d-%B-%Y",
    "%Y-%b-%d",
    "%Y-%B-%d",
    "%Y%m%d",
)


def build_chat_system_prompt(
    profile: Optional[Any] = None,
    facts: Optional[list[Any]] = None,
    recent_turns: Optional[list[Any]] = None,
    current_message: Optional[str] = None,
) -> str:
    """Build the conversational system prompt including persona, profile, memory facts, and recent turns."""
    system_parts = [CONVERSATIONAL_ASTROLOGY_SYSTEM_PROMPT]
    if profile is not None:
        if hasattr(profile, "model_dump_json"):
            profile_json = profile.model_dump_json(exclude_none=True)
        elif isinstance(profile, dict):
            profile_json = json.dumps(profile)
        else:
            profile_json = str(profile)
        system_parts.append(f"User profile: {profile_json}")
    if facts:
        facts_text = "\n".join(
            f"- [{getattr(f, 'type', 'fact')}] {getattr(f, 'key', '')}: {getattr(f, 'value', '')} {getattr(f, 'metadata', {}) if getattr(f, 'metadata', None) else ''}".rstrip()
            for f in facts
        )
        system_parts.append(f"Relevant long-term memory:\n{facts_text}")
    if recent_turns:
        history_turns = list(recent_turns)
        if history_turns:
            last = history_turns[-1]
            last_role = getattr(last, "role", last.get("role", "") if isinstance(last, dict) else "")
            last_content = getattr(last, "content", last.get("content", "") if isinstance(last, dict) else "")
            if last_role == "user" and (current_message is None or last_content == current_message):
                history_turns = history_turns[:-1]
        history = "\n".join(
            f"{getattr(t, 'role', t.get('role', '') if isinstance(t, dict) else '')}: {getattr(t, 'content', t.get('content', '') if isinstance(t, dict) else '')}"
            for t in history_turns
        )
        if history:
            system_parts.append(f"Recent conversation:\n{history}")
    return "\n\n".join(system_parts)


def build_chat_messages(
    message: str,
    profile: Optional[Any] = None,
    facts: Optional[list[Any]] = None,
    recent_turns: Optional[list[Any]] = None,
) -> list[dict[str, str]]:
    """Build the standard message payload for chat generation."""
    return [
        {"role": "system", "content": build_chat_system_prompt(profile, facts, recent_turns, current_message=message)},
        {"role": "user", "content": message},
    ]


def build_multi_turn_chat_messages(
    message: str,
    profile: Optional[Any] = None,
    facts: Optional[list[Any]] = None,
    recent_turns: Optional[list[Any]] = None,
) -> list[dict[str, str]]:
    """
    Build a multi-turn chat messages payload where previous turns are represented
    as discrete user/assistant message items following the system prompt.
    """
    messages: list[dict[str, str]] = [
        {"role": "system", "content": build_chat_system_prompt(profile, facts, recent_turns=None)}
    ]
    if recent_turns:
        history_turns = list(recent_turns)
        if history_turns:
            last = history_turns[-1]
            last_role = getattr(last, "role", last.get("role", "") if isinstance(last, dict) else "")
            last_content = getattr(last, "content", last.get("content", "") if isinstance(last, dict) else "")
            if last_role == "user" and last_content == message:
                history_turns = history_turns[:-1]
        for t in history_turns:
            role = getattr(t, "role", t.get("role", "") if isinstance(t, dict) else "")
            content = getattr(t, "content", t.get("content", "") if isinstance(t, dict) else "")
            if role and content:
                messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})
    return messages


def build_fact_extraction_prompt(text: str) -> str:
    """Format the fact extraction user prompt for a given user message."""
    return FACT_EXTRACTION_USER_PROMPT_TEMPLATE.format(text=text)


def build_fact_extraction_messages(text: str) -> list[dict[str, str]]:
    """Build system and user messages for structured fact extraction."""
    return [
        {"role": "system", "content": FACT_EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": build_fact_extraction_prompt(text)},
    ]


def parse_flexible_date(val: Any) -> Optional[date]:
    """
    Parse a date from diverse representations (ISO, non-ISO formats,
    conversational phrasing, relative month offsets, timestamps) or return None gracefully.
    """
    if val is None:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    if not isinstance(val, str):
        val = str(val)

    clean = val.strip().strip("\"'").strip()
    if not clean:
        return None

    # Handle ISO datetime string like "2004-06-26T14:30:00Z" or "2004-06-26 14:30:00"
    if "T" in clean:
        clean = clean.split("T")[0].strip()
    elif " " in clean and re.match(r"^\d{4}-\d{2}-\d{2}\s", clean):
        clean = clean.split(" ")[0].strip()

    # Try standard date.fromisoformat first
    try:
        return date.fromisoformat(clean)
    except ValueError:
        pass

    # Strip conversational prefixes: "i was born on", "born on", "born in", "born", "dob:", "date of birth:"
    clean_no_prefix = re.sub(
        r"^(?:(?:i\s+was\s+)?born(?:\s+on|\s+in)?|dob\s*:?|date\s+of\s+birth\s*:?)\s*",
        "",
        clean,
        flags=re.IGNORECASE,
    ).strip()

    # Strip trailing location phrases: e.g. "in Delhi", ", Delhi"
    clean_no_suffix = re.sub(
        r"(\d{4})\s+(?:in|at)\s+[A-Za-z\s,]+$",
        r"\1",
        clean_no_prefix,
        flags=re.IGNORECASE,
    ).strip()
    clean_no_suffix = re.sub(
        r"(\d{4})\s*,\s*[A-Za-z\s]+$",
        r"\1",
        clean_no_suffix,
        flags=re.IGNORECASE,
    ).strip()

    # Remove filler words: "of", "the" between day and month
    clean_no_filler = re.sub(r"\b(?:of|the)\b", " ", clean_no_suffix, flags=re.IGNORECASE)

    # Normalize ordinal suffixes: "15th" -> "15", "1st" -> "1", "2nd" -> "2", "3rd" -> "3"
    clean_ord = re.sub(r"\b(\d{1,2})(?:st|nd|rd|th)\b", r"\1", clean_no_filler, flags=re.IGNORECASE)

    # Normalize punctuation and extra spaces
    clean_norm = re.sub(r"[,/.-]", " ", clean_ord)
    clean_norm = re.sub(r"\s+", " ", clean_norm).strip()

    # Try strptime with common formats
    for fmt in _COMMON_DATE_FORMATS:
        for candidate in (clean_no_suffix, clean_ord, clean_norm):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                pass

    # Loose ISO: YYYY-M-D, YYYY/M/D, YYYY.M.D
    iso_loose = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$", clean_ord.strip())
    if iso_loose:
        try:
            return date(int(iso_loose.group(1)), int(iso_loose.group(2)), int(iso_loose.group(3)))
        except ValueError:
            pass

    # Loose DMY or MDY: D-M-YYYY, D/M/YYYY, D.M.YYYY
    dmy_loose = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$", clean_ord.strip())
    if dmy_loose:
        first, second, year = int(dmy_loose.group(1)), int(dmy_loose.group(2)), int(dmy_loose.group(3))
        if first > 12:
            try:
                return date(year, second, first)
            except ValueError:
                pass
        else:
            try:
                return date(year, second, first)
            except ValueError:
                try:
                    return date(year, first, second)
                except ValueError:
                    pass

    # Natural relative month offset: e.g. "born in 2004 on 3rd month from march and on 26th"
    # or "3 months after march 2004 on 26th", "third month after march 2004 on 26th",
    # "1 month after december 1999 on 15th"
    rel_match = re.search(
        r"(\w+)\s+months?\s+(?:from|after|before)\s+([a-zA-Z]+)",
        clean,
        re.IGNORECASE,
    )
    if rel_match:
        offset_raw = rel_match.group(1).lower()
        offset = _WORD_NUMBERS.get(offset_raw)
        if offset is None and offset_raw.isdigit():
            offset = int(offset_raw)
        base_month_name = rel_match.group(2).lower()
        if offset is not None and base_month_name in _MONTHS_MAP:
            base_month = _MONTHS_MAP[base_month_name]
            is_before = "before" in rel_match.group(0).lower()
            effective_offset = -offset if is_before else offset

            year_match = re.search(r"\b(19\d\d|20\d\d)\b", clean)
            day_match = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\b(?!\s*month)", clean_ord, re.IGNORECASE)
            if day_match and year_match:
                base_year = int(year_match.group(1))
                total_month = base_month + effective_offset
                target_year = base_year + (total_month - 1) // 12
                target_month = ((total_month - 1) % 12) + 1
                try:
                    return date(target_year, target_month, int(day_match.group(1)))
                except ValueError:
                    pass

    # If the text has an embedded ISO date: e.g. "born on 1995-08-15 in Mumbai"
    iso_embedded = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", clean)
    if iso_embedded:
        try:
            return date.fromisoformat(iso_embedded.group(1))
        except ValueError:
            pass

    return None


def _normalize_fact_list(val: Any) -> Optional[list[dict]]:
    """Helper to extract a valid list of fact dictionaries from parsed JSON structures."""
    if isinstance(val, list):
        if all(isinstance(item, dict) for item in val):
            return val
        return None
    if isinstance(val, dict):
        for key in ("facts", "data", "results", "candidates", "memory_facts"):
            if key in val and isinstance(val[key], list) and all(isinstance(item, dict) for item in val[key]):
                return val[key]
        for v in val.values():
            if isinstance(v, list) and v and all(isinstance(item, dict) for item in v):
                return v
        if "type" in val or "key" in val:
            return [val]
    return None


def parse_extracted_facts_json(raw: str) -> list[dict]:
    """
    Robust parser for LLM fact extraction responses.
    Handles raw JSON arrays, markdown fenced code blocks, object wrappers,
    leading/trailing commentary, and graceful fallback to empty list.
    """
    if not raw or not isinstance(raw, str):
        return []
    clean = raw.strip()
    if not clean:
        return []

    # 1. Check for markdown code fences: ```json ... ``` or ``` ... ```
    fence_matches = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", clean, flags=re.IGNORECASE)
    for block in fence_matches:
        try:
            val = json.loads(block.strip())
            norm = _normalize_fact_list(val)
            if norm is not None:
                return norm
        except Exception:
            pass

    # 2. Try parsing the whole string directly
    try:
        val = json.loads(clean)
        norm = _normalize_fact_list(val)
        if norm is not None:
            return norm
    except Exception:
        pass

    # 3. Use JSONDecoder to scan for candidate JSON array or object
    decoder = json.JSONDecoder()
    for i, ch in enumerate(clean):
        if ch in ("[", "{"):
            try:
                val, _ = decoder.raw_decode(clean[i:])
                norm = _normalize_fact_list(val)
                if norm is not None:
                    return norm
            except Exception:
                continue

    return []


__all__ = [
    "CONVERSATIONAL_ASTROLOGY_SYSTEM_PROMPT",
    "FACT_EXTRACTION_SYSTEM_PROMPT",
    "FACT_EXTRACTION_USER_PROMPT_TEMPLATE",
    "build_chat_system_prompt",
    "build_chat_messages",
    "build_multi_turn_chat_messages",
    "build_fact_extraction_prompt",
    "build_fact_extraction_messages",
    "parse_flexible_date",
    "parse_extracted_facts_json",
]
