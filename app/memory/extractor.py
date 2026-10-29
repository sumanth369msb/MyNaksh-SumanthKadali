import re
from datetime import datetime, timezone

from app.brain.models import CandidateFact

MONTHS = {
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

GREETING_ONLY_PATTERN = r"^\s*(?:hi|hello|hey|thanks|thank you|ok|okay)(?:\s+there)?[\s,!.]*$"
GREETING_PREFIX_PATTERN = r"^\s*(?:hi|hello|hey|thanks|thank you|ok|okay)(?:\s+there)?[\s,!.]+\s*"

GOAL_INTENT_KEYWORDS = [
    "planning", "preparing", "want", "switch", "change", "transition",
    "interview", "goal", "aim", "target", "prepare", "looking",
]

NAME_EXCLUSIONS = {
    "planning", "looking", "confused", "trying", "born", "hoping",
    "ready", "happy", "interested", "seeking", "wondering", "feeling",
    "working", "switching", "a", "an", "the", "not", "just", "also",
    "currently", "preparing", "wanting", "going", "thinking", "sure",
}

KNOWN_LANGUAGES = {
    "hindi", "english", "tamil", "telugu", "kannada", "malayalam",
    "marathi", "bengali", "gujarati", "punjabi", "urdu", "french",
    "spanish", "german", "sanskrit",
}

RELATION_MAP = {
    "goal": "HAS_GOAL",
    "preference": "PREFERS",
    "interest": "INTERESTED_IN",
    "profile": "HAS_PROFILE",
    "zodiac": "HAS_FACT",
}


class RuleBasedExtractor:
    def _is_interrogative(self, text: str) -> bool:
        lower = text.strip().lower()
        patterns = [
            r"^\s*why\s+do\s+you\s+say\s+that\b[^.?!\n]*[\s?!.]*$",
            r"^\s*what\s+do\s+you\s+remember(?:\s+about\b[^.?!\n]*)?[\s?!.]*$",
            r"^\s*what\s+do\s+you\s+know(?:\s+about\b[^.?!\n]*)?[\s?!.]*$",
        ]
        return any(re.match(p, lower) for p in patterns)

    def extract(self, user_id: str, message: str) -> list[CandidateFact]:
        clean = message.strip()
        lower = clean.lower()

        # If message is solely a greeting or pleasantry, ignore it
        if re.match(GREETING_ONLY_PATTERN, lower):
            return []

        # If message is an interrogative meta-question, ignore it
        if self._is_interrogative(clean):
            return []

        # Strip leading greeting prefix if present before extracting substantive facts
        clean_for_extraction = re.sub(GREETING_PREFIX_PATTERN, "", clean, count=1, flags=re.I).strip()
        if not clean_for_extraction:
            return []
        lower_extracted = clean_for_extraction.lower()

        facts: list[CandidateFact] = []

        # Name extraction: first try explicit "my name is <Name>", else "I am / I'm <Name>", else "call myself <Name>"
        name_match = re.search(r"\bmy name is\s+([A-Za-z][A-Za-z\-']*)", clean_for_extraction, re.I)
        if name_match:
            candidate_name = name_match.group(1).strip()
            if candidate_name.lower() not in NAME_EXCLUSIONS:
                facts.append(CandidateFact(
                    type="profile",
                    key="name",
                    value=candidate_name,
                    relation="HAS_PROFILE",
                    confidence=0.9,
                ))
        else:
            call_match = re.search(r"\b(?:call myself|like to call myself|prefer to be called)\s+([A-Za-z][A-Za-z\-']*)", clean_for_extraction, re.I)
            if call_match:
                candidate_name = call_match.group(1).strip()
                if candidate_name.lower() not in NAME_EXCLUSIONS:
                    facts.append(CandidateFact(
                        type="profile",
                        key="name",
                        value=candidate_name,
                        relation="HAS_PROFILE",
                        confidence=0.9,
                    ))
            else:
                iam_match = re.search(r"\b(?:i am|i'm|I am|I'm)\s+([A-Z][A-Za-z\-']*)", clean_for_extraction)
                if iam_match:
                    candidate_name = iam_match.group(1).strip()
                    if candidate_name.lower() not in NAME_EXCLUSIONS:
                        facts.append(CandidateFact(
                            type="profile",
                            key="name",
                            value=candidate_name,
                            relation="HAS_PROFILE",
                            confidence=0.9,
                        ))

        dob_match = re.search(r"\bborn on\s+(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(\d{4})\b", clean_for_extraction, re.I)
        if dob_match:
            day, month_name, year = dob_match.groups()
            month = MONTHS.get(month_name.lower())
            if month:
                facts.append(CandidateFact(
                    type="profile",
                    key="date_of_birth",
                    value=f"{year}-{month:02d}-{int(day):02d}",
                    relation="HAS_PROFILE",
                    confidence=0.9,
                ))
        else:
            dob_mdy_match = re.search(r"\bborn on\s+([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", clean_for_extraction, re.I)
            if dob_mdy_match:
                month_name, day, year = dob_mdy_match.groups()
                month = MONTHS.get(month_name.lower())
                if month:
                    facts.append(CandidateFact(
                        type="profile",
                        key="date_of_birth",
                        value=f"{year}-{month:02d}-{int(day):02d}",
                        relation="HAS_PROFILE",
                        confidence=0.9,
                    ))

        if not any(f.key == "date_of_birth" for f in facts):
            from app.llm.prompts import parse_flexible_date
            parsed_dob = parse_flexible_date(clean_for_extraction)
            if parsed_dob:
                facts.append(CandidateFact(
                    type="profile",
                    key="date_of_birth",
                    value=parsed_dob.isoformat(),
                    relation="HAS_PROFILE",
                    confidence=0.85,
                ))

        place_match = re.search(
            r"(?:\bborn in|\bborn on\s+(?:\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+|[A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,?)\s+\d{4}\s+in)\s+([A-Za-z][A-Za-z\s,]*?)(?:\.|$|,|\b(?:and|with|at)\b)",
            clean_for_extraction,
            re.I,
        )
        if place_match:
            val = place_match.group(1).strip().rstrip(",.")
            if val:
                facts.append(CandidateFact(
                    type="profile",
                    key="birth_place",
                    value=val,
                    relation="HAS_PROFILE",
                    confidence=0.85,
                ))

        # Token-based language preference extraction
        if any(k in lower_extracted for k in ("prefer", "preferred", "language", "speak", "reply", "respond")):
            words = re.findall(r"[A-Za-z]+", clean_for_extraction)
            found_lang = None
            for w in words:
                if w.lower() in KNOWN_LANGUAGES:
                    found_lang = w.capitalize()
                    break
            if not found_lang:
                lang_match = re.search(
                    r"(?:prefer(?:red)?\s+language\s*(?:is|to|in|:)?|prefer\s+to\s+speak|prefer\s+speaking)\s+([A-Za-z]+)",
                    clean_for_extraction,
                    re.I,
                )
                if lang_match:
                    cand = lang_match.group(1).strip()
                    if cand.lower() not in {"to", "a", "the", "in", "with", "speaking", "language", "is"}:
                        found_lang = cand.capitalize()
            if found_lang:
                facts.append(CandidateFact(
                    type="preference",
                    key="language",
                    value=found_lang,
                    relation="PREFERS",
                    confidence=0.85,
                ))

        interest_match = re.search(r"\binterested in\s+([A-Za-z][A-Za-z\s]*?)(?:\.|$|,)", clean_for_extraction, re.I)
        if interest_match:
            val = interest_match.group(1).strip().rstrip(",.")
            if val:
                facts.append(CandidateFact(
                    type="interest",
                    key="interest",
                    value=val,
                    relation="INTERESTED_IN",
                    confidence=0.8,
                ))

        memory_match = re.search(r"\b(?:important memory|key memory|cherished memory|milestone)(?:\s+for me)?\s+(?:is|was)\s+([^.,;\n]+)", clean_for_extraction, re.I)
        if memory_match:
            val = memory_match.group(1).strip().rstrip(",.")
            if val:
                facts.append(CandidateFact(
                    type="memory",
                    key="milestone",
                    value=val,
                    relation="HAS_FACT",
                    confidence=0.85,
                ))

        life_area_match = re.search(r"\b(?:key life areas?|life areas?|focus areas?)\s+(?:are|is)\s+([^.,;\n]+)", clean_for_extraction, re.I)
        if life_area_match:
            val = life_area_match.group(1).strip().rstrip(",.")
            if val:
                facts.append(CandidateFact(
                    type="life_area",
                    key="priority",
                    value=val,
                    relation="HAS_FACT",
                    confidence=0.85,
                ))

        has_goal_intent = any(k in lower_extracted for k in GOAL_INTENT_KEYWORDS)
        has_career_domain = any(k in lower_extracted for k in ["career", "job", "interview", "switch", "product manager", "entrepreneur"])
        if has_goal_intent and has_career_domain:
            timeframe = None
            if "next year" in lower_extracted:
                timeframe = str(datetime.now(timezone.utc).year + 1)
            if "next month" in lower_extracted:
                timeframe = "next month"
            year_match = re.search(r"\b(202\d)\b", clean_for_extraction)
            if year_match:
                timeframe = year_match.group(1)
            facts.append(CandidateFact(
                type="goal",
                key="career",
                value=clean_for_extraction,
                relation="HAS_GOAL",
                confidence=0.75,
                metadata={"timeframe": timeframe} if timeframe else {},
            ))
        elif "goal" in lower_extracted and not any(f.type == "goal" for f in facts):
            facts.append(CandidateFact(
                type="goal",
                key="general",
                value=clean_for_extraction,
                relation="HAS_GOAL",
                confidence=0.6,
            ))

        unique = []
        seen = set()
        for fact in facts:
            signature = (fact.type, fact.key, fact.value)
            if signature in seen:
                continue
            seen.add(signature)
            unique.append(fact)
        return unique


class HybridExtractor:
    def __init__(self, llm_provider=None):
        self.rules = RuleBasedExtractor()
        self.llm_provider = llm_provider

    async def extract(self, user_id: str, message: str) -> list[CandidateFact]:
        facts = self.rules.extract(user_id, message)
        if self.llm_provider is not None:
            try:
                extracted = await self.llm_provider.extract_facts(message)
                for item in extracted:
                    fact_type = item.get("type", "memory")
                    default_rel = RELATION_MAP.get(fact_type, "HAS_FACT")
                    facts.append(CandidateFact(
                        type=fact_type,
                        key=item.get("key", "fact"),
                        value=item.get("value", ""),
                        relation=item.get("relation", default_rel),
                        confidence=float(item.get("confidence", 0.7)),
                        metadata=item.get("metadata", {}),
                    ))
            except Exception:
                pass

        unique = []
        seen = set()
        for fact in facts:
            signature = (fact.type, fact.key, fact.value)
            if signature in seen:
                continue
            seen.add(signature)
            unique.append(fact)
        return unique
