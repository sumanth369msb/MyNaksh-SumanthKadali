from datetime import date, datetime
from unittest.mock import AsyncMock
import pytest

from app.api.schemas import ProfilePayload
from app.brain.models import MemoryFact
from app.chat.service import ChatService
from app.llm.openai import OpenAIProvider
from app.llm.prompts import (
    CONVERSATIONAL_ASTROLOGY_SYSTEM_PROMPT,
    FACT_EXTRACTION_SYSTEM_PROMPT,
    FACT_EXTRACTION_USER_PROMPT_TEMPLATE,
    build_chat_messages,
    build_chat_system_prompt,
    build_multi_turn_chat_messages,
    build_fact_extraction_messages,
    build_fact_extraction_prompt,
    parse_extracted_facts_json,
    parse_flexible_date,
)
from app.profile.models import ProfileUpdate, UserProfile


# ============================================================================
# 1. System Prompt & Persona Tests
# ============================================================================

def test_system_prompt_contains_jungian_and_vedic_persona():
    prompt_lower = CONVERSATIONAL_ASTROLOGY_SYSTEM_PROMPT.lower()
    assert "vedic" in prompt_lower
    assert "jungian" in prompt_lower
    assert "archetype" in prompt_lower


def test_system_prompt_contains_ethical_safety_boundaries():
    prompt_lower = CONVERSATIONAL_ASTROLOGY_SYSTEM_PROMPT.lower()
    # Anti-fatalism / Free will
    assert "fatalis" in prompt_lower or "agency" in prompt_lower
    assert "free will" in prompt_lower or "agency" in prompt_lower
    # Medical safety
    assert "medical" in prompt_lower
    # Financial safety
    assert "financial" in prompt_lower


def test_system_prompt_contains_empathy_and_conciseness():
    prompt_lower = CONVERSATIONAL_ASTROLOGY_SYSTEM_PROMPT.lower()
    assert "empath" in prompt_lower or "warm" in prompt_lower
    assert "concise" in prompt_lower or "digestible" in prompt_lower


def test_build_chat_system_prompt_empty():
    system_prompt = build_chat_system_prompt()
    assert CONVERSATIONAL_ASTROLOGY_SYSTEM_PROMPT in system_prompt
    assert "User profile:" not in system_prompt
    assert "Relevant long-term memory:" not in system_prompt
    assert "Recent conversation:" not in system_prompt


def test_build_chat_system_prompt_with_profile():
    profile = UserProfile(user_id="u123", name="Aditi", date_of_birth=date(1998, 10, 22), zodiac="Libra")
    system_prompt = build_chat_system_prompt(profile=profile)
    assert "User profile:" in system_prompt
    assert "Aditi" in system_prompt
    assert "1998-10-22" in system_prompt
    assert "Libra" in system_prompt


def test_build_chat_system_prompt_with_facts():
    facts = [
        MemoryFact(user_id="u123", type="interest", key="hobby", value="astronomy", relation="INTERESTED_IN"),
        MemoryFact(user_id="u123", type="preference", key="language", value="Hindi", relation="PREFERS"),
    ]
    system_prompt = build_chat_system_prompt(facts=facts)
    assert "Relevant long-term memory:" in system_prompt
    assert "- [interest] hobby: astronomy" in system_prompt
    assert "- [preference] language: Hindi" in system_prompt


def test_build_chat_system_prompt_with_history():
    class Turn:
        def __init__(self, role, content):
            self.role = role
            self.content = content

    turns = [
        Turn("user", "Hello there"),
        Turn("assistant", "Greetings! How can I guide you today?"),
        Turn("user", "What is my sun sign?"),  # Last turn (current message) should be excluded from history
    ]
    system_prompt = build_chat_system_prompt(recent_turns=turns)
    assert "Recent conversation:" in system_prompt
    assert "user: Hello there" in system_prompt
    assert "assistant: Greetings! How can I guide you today?" in system_prompt
    assert "What is my sun sign?" not in system_prompt


def test_build_chat_system_prompt_preserves_assistant_last_turn():
    class Turn:
        def __init__(self, role, content):
            self.role = role
            self.content = content

    # When history ends with an assistant turn (prior response), it must NOT be dropped!
    turns = [
        Turn("user", "I live in Delhi"),
        Turn("assistant", "Delhi is vibrant! How can I assist you today?"),
    ]
    system_prompt = build_chat_system_prompt(recent_turns=turns)
    assert "user: I live in Delhi" in system_prompt
    assert "assistant: Delhi is vibrant! How can I assist you today?" in system_prompt


def test_build_chat_messages_structure():
    messages = build_chat_messages(
        message="Guide me through this transition.",
        profile=UserProfile(user_id="u1", name="Karan"),
        facts=[],
        recent_turns=[],
    )
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert "Karan" in messages[0]["content"]
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "Guide me through this transition."


def test_build_multi_turn_chat_messages_structure():
    class Turn:
        def __init__(self, role, content):
            self.role = role
            self.content = content

    turns = [
        Turn("user", "Hello there"),
        Turn("assistant", "Greetings! How may I assist you?"),
        Turn("user", "What is my sun sign?"),
    ]
    messages = build_multi_turn_chat_messages(
        message="What is my sun sign?",
        profile=UserProfile(user_id="u1", name="Karan"),
        facts=[],
        recent_turns=turns,
    )
    assert len(messages) == 4
    assert messages[0]["role"] == "system"
    assert "Karan" in messages[0]["content"]
    assert messages[1] == {"role": "user", "content": "Hello there"}
    assert messages[2] == {"role": "assistant", "content": "Greetings! How may I assist you?"}
    assert messages[3] == {"role": "user", "content": "What is my sun sign?"}


# ============================================================================
# 2. Fact Extraction Prompt Tests
# ============================================================================

def test_fact_extraction_prompt_mentions_iso_format():
    template = FACT_EXTRACTION_USER_PROMPT_TEMPLATE
    assert "ISO-8601" in template or "YYYY-MM-DD" in template
    assert "date.fromisoformat()" in template


def test_fact_extraction_prompt_mentions_relative_date_normalization():
    template = FACT_EXTRACTION_USER_PROMPT_TEMPLATE
    assert "born in 2004 on 3rd month from march and on 26th" in template
    assert "2004-06-26" in template


def test_build_fact_extraction_prompt_interpolation():
    msg = "I was born on August 15, 1995 in Mumbai."
    prompt = build_fact_extraction_prompt(msg)
    assert f"Message: {msg}" in prompt
    assert "YYYY-MM-DD" in prompt


def test_build_fact_extraction_messages_roles():
    messages = build_fact_extraction_messages("My name is Maya.")
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == FACT_EXTRACTION_SYSTEM_PROMPT
    assert messages[1]["role"] == "user"
    assert "My name is Maya." in messages[1]["content"]


# ============================================================================
# 3. Flexible Date Parsing Tests
# ============================================================================

@pytest.mark.parametrize(
    "input_val,expected",
    [
        # Standard ISO-8601
        ("2004-06-26", date(2004, 6, 26)),
        ("1995-08-15", date(1995, 8, 15)),
        ("2000-01-01", date(2000, 1, 1)),
        # Loose ISO (single-digit month or day, slash or dot separators)
        ("2004-6-26", date(2004, 6, 26)),
        ("2004/6/26", date(2004, 6, 26)),
        ("1995/08/15", date(1995, 8, 15)),
        ("2004.06.26", date(2004, 6, 26)),
        ("2004.6.26", date(2004, 6, 26)),
        ("19950815", date(1995, 8, 15)),
        # Quoted / Padded strings
        ('  "1995-08-15"  ', date(1995, 8, 15)),
        ("'2004-06-26'", date(2004, 6, 26)),
        # ISO timestamp strings
        ("2004-06-26T14:30:00Z", date(2004, 6, 26)),
        ("1995-08-15 09:15:00", date(1995, 8, 15)),
        # DD-MM-YYYY, DD/MM/YYYY, DD.MM.YYYY
        ("15/08/1995", date(1995, 8, 15)),
        ("15-08-1995", date(1995, 8, 15)),
        ("15.08.1995", date(1995, 8, 15)),
        ("26-06-2004", date(2004, 6, 26)),
        ("26/06/2004", date(2004, 6, 26)),
        ("26.06.2004", date(2004, 6, 26)),
        # Full Month Name
        ("15 August 1995", date(1995, 8, 15)),
        ("August 15, 1995", date(1995, 8, 15)),
        ("August 15 1995", date(1995, 8, 15)),
        ("26 June 2004", date(2004, 6, 26)),
        ("June 26, 2004", date(2004, 6, 26)),
        # Abbreviated Month Name
        ("15 Aug 1995", date(1995, 8, 15)),
        ("Aug 15, 1995", date(1995, 8, 15)),
        ("26 Jun 2004", date(2004, 6, 26)),
        # Ordinal Suffixes & Fillers ("of", "the")
        ("15th August 1995", date(1995, 8, 15)),
        ("15th of August 1995", date(1995, 8, 15)),
        ("15th of August, 1995", date(1995, 8, 15)),
        ("1st January 2000", date(2000, 1, 1)),
        ("2nd February 1990", date(1990, 2, 2)),
        ("3rd March 2004", date(2004, 3, 3)),
        ("22nd October 1998", date(1998, 10, 22)),
        ("August 15th, 1995", date(1995, 8, 15)),
        ("August the 15th, 1995", date(1995, 8, 15)),
        ("26th of June, 2004", date(2004, 6, 26)),
        ("June the 26th, 2004", date(2004, 6, 26)),
        # Conversational Prefixes & Locations
        ("born 15 August 1995", date(1995, 8, 15)),
        ("born on 15th August 1995", date(1995, 8, 15)),
        ("born on August 15, 1995", date(1995, 8, 15)),
        ("born 2004-06-26", date(2004, 6, 26)),
        ("born on 22nd October 1998", date(1998, 10, 22)),
        ("born on 22nd October 1998 in Mumbai", date(1998, 10, 22)),
        ("15th August 1995, Delhi", date(1995, 8, 15)),
        ("DOB: 1995-08-15", date(1995, 8, 15)),
        ("date of birth: 1995-08-15", date(1995, 8, 15)),
        # Relative verbal expressions (digits, words, plurals, before, cross-year rollovers)
        ("born in 2004 on 3rd month from march and on 26th", date(2004, 6, 26)),
        ("3rd month from march 2004 on 26th", date(2004, 6, 26)),
        ("3 months after march 2004 on 26th", date(2004, 6, 26)),
        ("third month after march 2004 on 26th", date(2004, 6, 26)),
        ("2nd month after january 2005 on 15th", date(2005, 3, 15)),
        ("1 month after december 1999 on 15th", date(2000, 1, 15)),
        ("1 month before january 2000 on 15th", date(1999, 12, 15)),
        ("two months before march 2004 on 10th", date(2004, 1, 10)),
        # Embedded ISO dates in text
        ("My birth date is 2004-06-26 according to my records", date(2004, 6, 26)),
        # Type passthroughs
        (date(2004, 6, 26), date(2004, 6, 26)),
        (datetime(2004, 6, 26, 10, 0), date(2004, 6, 26)),
    ],
)
def test_parse_flexible_date_valid(input_val, expected):
    assert parse_flexible_date(input_val) == expected


@pytest.mark.parametrize(
    "invalid_input",
    [
        None,
        "",
        "   ",
        "not-a-date",
        "someday in the future",
        "2024-99-99",
        12345,
        {},
        [],
    ],
)
def test_parse_flexible_date_invalid_graceful(invalid_input):
    assert parse_flexible_date(invalid_input) is None


# ============================================================================
# 4. JSON Fact Extraction Parser Tests
# ============================================================================

def test_parse_extracted_facts_json_clean_array():
    raw = '[{"type": "profile", "key": "name", "value": "Rahul"}]'
    facts = parse_extracted_facts_json(raw)
    assert facts == [{"type": "profile", "key": "name", "value": "Rahul"}]


def test_parse_extracted_facts_json_markdown_fence_with_trailing_commentary():
    raw = (
        'Here is the extracted information:\n```json\n'
        '[\n'
        '  {"type": "profile", "key": "date_of_birth", "value": "1995-08-15"}\n'
        ']\n```\n'
        'Note: [Confidence is high]'
    )
    facts = parse_extracted_facts_json(raw)
    assert len(facts) == 1
    assert facts[0]["key"] == "date_of_birth"
    assert facts[0]["value"] == "1995-08-15"


def test_parse_extracted_facts_json_leading_bracket_commentary():
    raw = (
        '[Important note about facts]\n'
        '[\n'
        '  {"type": "goal", "key": "career", "value": "Transitioning to PM"}\n'
        ']'
    )
    facts = parse_extracted_facts_json(raw)
    assert len(facts) == 1
    assert facts[0]["key"] == "career"
    assert facts[0]["value"] == "Transitioning to PM"


def test_parse_extracted_facts_json_wrapped_in_object():
    raw = (
        '{\n'
        '  "tags": ["user", "profile"],\n'
        '  "facts": [\n'
        '    {"type": "profile", "key": "birth_place", "value": "Varanasi"}\n'
        '  ]\n'
        '}'
    )
    facts = parse_extracted_facts_json(raw)
    assert len(facts) == 1
    assert facts[0]["key"] == "birth_place"
    assert facts[0]["value"] == "Varanasi"


def test_parse_extracted_facts_json_single_dict():
    raw = '{"type": "profile", "key": "name", "value": "Ananya"}'
    facts = parse_extracted_facts_json(raw)
    assert len(facts) == 1
    assert facts[0]["key"] == "name"
    assert facts[0]["value"] == "Ananya"


def test_parse_extracted_facts_json_invalid_graceful():
    assert parse_extracted_facts_json("I cannot extract any facts.") == []
    assert parse_extracted_facts_json("") == []
    assert parse_extracted_facts_json(None) == []


# ============================================================================
# 5. Profile Fact Application & Model Validator Tests
# ============================================================================

@pytest.mark.asyncio
async def test_apply_profile_fact_iso_dob():
    service = ChatService()
    profile = UserProfile(user_id="u1")
    fact = MemoryFact(user_id="u1", type="profile", key="date_of_birth", value="1995-08-15")
    await service._apply_profile_fact(profile, fact)
    assert profile.date_of_birth == date(1995, 8, 15)
    assert profile.zodiac == "Leo"


@pytest.mark.asyncio
async def test_apply_profile_fact_non_iso_dob():
    service = ChatService()
    profile = UserProfile(user_id="u1")
    fact = MemoryFact(user_id="u1", type="profile", key="date_of_birth", value="15th August 1995")
    await service._apply_profile_fact(profile, fact)
    assert profile.date_of_birth == date(1995, 8, 15)
    assert profile.zodiac == "Leo"


@pytest.mark.asyncio
async def test_apply_profile_fact_synonym_keys():
    service = ChatService()
    profile = UserProfile(user_id="u1")

    # dob synonym
    await service._apply_profile_fact(profile, MemoryFact(user_id="u1", type="profile", key="dob", value="2004-06-26"))
    assert profile.date_of_birth == date(2004, 6, 26)
    assert profile.zodiac == "Cancer"

    # birthplace synonym
    await service._apply_profile_fact(profile, MemoryFact(user_id="u1", type="profile", key="birthplace", value="Mumbai"))
    assert profile.birth_place == "Mumbai"


@pytest.mark.asyncio
async def test_apply_profile_fact_relative_phrasing_dob():
    service = ChatService()
    profile = UserProfile(user_id="u1")
    fact = MemoryFact(
        user_id="u1",
        type="profile",
        key="date_of_birth",
        value="born in 2004 on 3rd month from march and on 26th",
    )
    await service._apply_profile_fact(profile, fact)
    assert profile.date_of_birth == date(2004, 6, 26)
    assert profile.zodiac == "Cancer"


@pytest.mark.asyncio
async def test_apply_profile_fact_invalid_dob_graceful():
    service = ChatService()
    profile = UserProfile(user_id="u1", date_of_birth=date(1990, 1, 1), zodiac="Capricorn")
    fact = MemoryFact(user_id="u1", type="profile", key="date_of_birth", value="unknown-date-string")
    await service._apply_profile_fact(profile, fact)
    # Remains unchanged and does not raise exception
    assert profile.date_of_birth == date(1990, 1, 1)
    assert profile.zodiac == "Capricorn"


@pytest.mark.asyncio
async def test_apply_profile_fact_name_and_place_and_language():
    service = ChatService()
    profile = UserProfile(user_id="u1")

    await service._apply_profile_fact(profile, MemoryFact(user_id="u1", type="profile", key="name", value="Aarav"))
    assert profile.name == "Aarav"

    await service._apply_profile_fact(profile, MemoryFact(user_id="u1", type="profile", key="birth_place", value="Varanasi"))
    assert profile.birth_place == "Varanasi"

    await service._apply_profile_fact(profile, MemoryFact(user_id="u1", type="preference", key="language", value="Hindi"))
    assert profile.preferred_language == "Hindi"


def test_user_profile_flexible_date_validator():
    profile = UserProfile(user_id="u1", date_of_birth="15th August 1995")
    assert profile.date_of_birth == date(1995, 8, 15)

    update = ProfileUpdate(date_of_birth="26th of June, 2004")
    assert update.date_of_birth == date(2004, 6, 26)

    payload = ProfilePayload(date_of_birth="2004.06.26")
    assert payload.date_of_birth == date(2004, 6, 26)


# ============================================================================
# 6. OpenAIProvider Fact Extraction Tests
# ============================================================================

@pytest.mark.asyncio
async def test_openai_provider_extract_facts_structured_json():
    provider = OpenAIProvider(api_key="test-key", base_url="https://mock.api", model="test-model")
    fake_json = (
        '[\n'
        '  {"type": "profile", "key": "date_of_birth", "value": "2004-06-26", "relation": "HAS_PROFILE", "confidence": 0.95, "metadata": {}},\n'
        '  {"type": "profile", "key": "birth_place", "value": "Delhi", "relation": "HAS_PROFILE", "confidence": 0.9, "metadata": {}}\n'
        ']'
    )
    provider.generate = AsyncMock(return_value=fake_json)

    facts = await provider.extract_facts("born in 2004 on 3rd month from march and on 26th in Delhi")
    assert len(facts) == 2
    assert facts[0]["key"] == "date_of_birth"
    assert facts[0]["value"] == "2004-06-26"
    assert facts[1]["key"] == "birth_place"
    assert facts[1]["value"] == "Delhi"

    # Verify that build_fact_extraction_messages was passed to generate
    assert provider.generate.called
    called_messages = provider.generate.call_args[0][0]
    assert called_messages[0]["content"] == FACT_EXTRACTION_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_openai_provider_extract_facts_handles_markdown_fence():
    provider = OpenAIProvider(api_key="test-key", base_url="https://mock.api", model="test-model")
    fake_response = (
        'Here are the extracted facts:\n```json\n'
        '[\n'
        '  {"type": "goal", "key": "career", "value": "Switching jobs in 2026", "relation": "HAS_GOAL", "confidence": 0.85, "metadata": {"timeframe": "2026"}}\n'
        ']\n```'
    )
    provider.generate = AsyncMock(return_value=fake_response)

    facts = await provider.extract_facts("I will switch jobs in 2026.")
    assert len(facts) == 1
    assert facts[0]["type"] == "goal"
    assert facts[0]["key"] == "career"
    assert facts[0]["metadata"]["timeframe"] == "2026"


@pytest.mark.asyncio
async def test_openai_provider_extract_facts_invalid_json_returns_empty():
    provider = OpenAIProvider(api_key="test-key", base_url="https://mock.api", model="test-model")
    provider.generate = AsyncMock(return_value="I am not able to extract any facts.")
    facts = await provider.extract_facts("Random text")
    assert facts == []
