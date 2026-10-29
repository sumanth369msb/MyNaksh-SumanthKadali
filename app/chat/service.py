from __future__ import annotations

import logging
from typing import Any, Optional

from app.astrology.calculator import compute_zodiac
from app.brain.factory import create_graph_store
from app.brain.models import MemoryFact
from app.brain.store import GraphStore
from app.context.selector import ContextSelector
from app.core.cache import TTLCache
from app.core.config import settings
from app.llm.factory import create_llm_provider
from app.llm.prompts import build_chat_messages, parse_flexible_date
from app.memory.extractor import HybridExtractor
from app.memory.short_term import ShortTermMemory
from app.profile.models import UserProfile

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(
        self,
        graph_store: GraphStore | None = None,
        llm_provider=None,
        short_term: ShortTermMemory | None = None,
        cache: TTLCache | None = None,
    ):
        self.graph_store = graph_store or create_graph_store()
        self.llm_provider = llm_provider or create_llm_provider()
        self.short_term = short_term or ShortTermMemory()
        self.cache = cache or TTLCache(settings.cache_ttl_seconds)
        self.selector = ContextSelector(settings.memory_top_k)
        self.extractor = HybridExtractor(self.llm_provider if settings.llm_provider != "mock" else None)

    async def startup(self) -> None:
        try:
            await self.graph_store.connect()
        except Exception as exc:
            logger.warning("Graph store connect failed: %s", exc)

    async def shutdown(self) -> None:
        try:
            await self.graph_store.close()
        except Exception:
            pass

    async def sync_profile_facts(self, profile: UserProfile) -> None:
        if not profile or not profile.user_id:
            return

        facts_to_sync: list[MemoryFact] = []
        if profile.name:
            facts_to_sync.append(MemoryFact(
                user_id=profile.user_id,
                type="profile",
                key="name",
                value=str(profile.name),
                relation="HAS_PROFILE",
                confidence=1.0,
                source="profile",
            ))
        if profile.date_of_birth:
            dob_val = (
                profile.date_of_birth.isoformat()
                if hasattr(profile.date_of_birth, "isoformat")
                else str(profile.date_of_birth)
            )
            facts_to_sync.append(MemoryFact(
                user_id=profile.user_id,
                type="profile",
                key="date_of_birth",
                value=dob_val,
                relation="HAS_PROFILE",
                confidence=1.0,
                source="profile",
            ))
        if profile.birth_place:
            facts_to_sync.append(MemoryFact(
                user_id=profile.user_id,
                type="profile",
                key="birth_place",
                value=str(profile.birth_place),
                relation="HAS_PROFILE",
                confidence=1.0,
                source="profile",
            ))
        if profile.time_of_birth:
            facts_to_sync.append(MemoryFact(
                user_id=profile.user_id,
                type="profile",
                key="time_of_birth",
                value=str(profile.time_of_birth),
                relation="HAS_PROFILE",
                confidence=1.0,
                source="profile",
            ))
        if profile.preferred_language:
            facts_to_sync.append(MemoryFact(
                user_id=profile.user_id,
                type="preference",
                key="language",
                value=str(profile.preferred_language),
                relation="PREFERS",
                confidence=1.0,
                source="profile",
            ))
        if profile.zodiac:
            facts_to_sync.append(MemoryFact(
                user_id=profile.user_id,
                type="zodiac",
                key="sun_sign",
                value=str(profile.zodiac),
                relation="HAS_FACT",
                confidence=1.0,
                source="profile",
            ))

        for fact in facts_to_sync:
            try:
                await self.graph_store.upsert_fact(fact)
            except Exception as exc:
                logger.warning("Failed to sync profile fact (%s): %s", fact.key, exc)

    async def chat(self, user_id: str, session_id: str, message: str, profile: Optional[UserProfile] = None) -> dict[str, Any]:
        if not message or not message.strip():
            raise ValueError("Message cannot be empty or whitespace")

        # 1. Append user turn to short-term session memory
        await self.short_term.add(session_id, "user", message)

        # 2. Upsert profile into store and sync profile facts if provided
        if profile is not None:
            profile.user_id = user_id
            if profile.date_of_birth is not None:
                profile.zodiac = compute_zodiac(profile.date_of_birth)
            try:
                await self.graph_store.upsert_user(profile)
                await self.sync_profile_facts(profile)
            except Exception as exc:
                logger.warning("Failed to upsert user / sync profile facts: %s", exc)

        # 3. Load merged user profile
        user_profile = await self._get_profile(user_id, profile)
        if user_profile is not None:
            try:
                await self.sync_profile_facts(user_profile)
            except Exception as exc:
                logger.warning("Failed to sync profile facts: %s", exc)

        # 4 & 5. Extract candidate facts from current message and upsert before context selection
        # (Strictly adheres to docs/context/technical_spec.md Section 1 steps 4 & 5 so single-turn
        # self-introductions immediately personalize the LLM context)
        try:
            user_profile = await self._update_memory(user_id, message, user_profile)
        except Exception as exc:
            logger.warning("Pre-selection memory update failed: %s", exc)

        # 6. Retrieve short-term turns and facts from graph store
        recent_turns = await self.short_term.get(session_id, limit=settings.short_term_max_messages)

        facts: list[MemoryFact] = []
        try:
            facts = await self.graph_store.get_facts(user_id, limit=50)
        except Exception as exc:
            logger.warning("Failed to get facts: %s", exc)

        # 7. Select relevant user context prior to LLM call
        selected_facts, context_used = self.selector.select(message, user_profile, facts, recent_turns)

        # 8. Build LLM context
        llm_messages = self._build_messages(message, user_profile, selected_facts, recent_turns)

        # 9. Generate Response (cached; fallback on failure)
        profile_sig = user_profile.model_dump(mode="json", exclude_none=True) if user_profile else None
        recent_sig = [(t.role, t.content) for t in recent_turns]
        cache_key = self.cache.make_key(
            user_id, session_id, message, [f.id for f in selected_facts], recent_sig, profile_sig
        )
        cached = self.cache.get(cache_key)
        if cached is not None:
            response_text = cached
        else:
            try:
                response_text = await self.llm_provider.generate(
                    llm_messages, temperature=settings.llm_temperature, max_tokens=settings.llm_max_tokens
                )
                self.cache.set(cache_key, response_text)
            except Exception as exc:
                logger.warning("LLM generation failed: %s", exc)
                response_text = self._fallback_response(user_profile, selected_facts)

        # 10. Append assistant turn to short-term session memory
        await self.short_term.add(session_id, "assistant", response_text)

        # 11. Return telemetry and response
        return {
            "response": response_text,
            "user_id": user_id,
            "session_id": session_id,
            "context_used": context_used,
        }

    async def _get_profile(self, user_id: str, provided: Optional[UserProfile]) -> Optional[UserProfile]:
        try:
            stored = await self.graph_store.get_user(user_id)
            if stored is not None:
                return stored
        except Exception:
            pass
        return provided

    def _build_messages(self, message, profile, facts, recent_turns):
        return build_chat_messages(message, profile, facts, recent_turns)

    async def _update_memory(self, user_id: str, message: str, profile: Optional[UserProfile]) -> Optional[UserProfile]:
        try:
            candidates = await self.extractor.extract(user_id, message)
            for candidate in candidates:
                fact = MemoryFact(
                    user_id=user_id,
                    type=candidate.type,
                    key=candidate.key,
                    value=candidate.value,
                    relation=candidate.relation,
                    confidence=candidate.confidence,
                    source=candidate.source,
                    metadata=candidate.metadata,
                )
                if fact.type == "profile" or (fact.type == "preference" and fact.key in ("language", "preferred_language")):
                    if profile is None:
                        profile = UserProfile(user_id=user_id)
                    await self._apply_profile_fact(profile, fact)
                    try:
                        await self.graph_store.upsert_user(profile)
                        await self.sync_profile_facts(profile)
                    except Exception as exc:
                        logger.warning("Failed to upsert user / sync profile facts: %s", exc)
                else:
                    try:
                        await self.graph_store.upsert_fact(fact)
                    except Exception as exc:
                        logger.warning("Failed to upsert fact: %s", exc)
        except Exception as exc:
            logger.warning("Memory update failed: %s", exc)
        return profile

    async def _apply_profile_fact(self, profile: UserProfile, fact: MemoryFact) -> None:
        if fact.key == "name":
            profile.name = str(fact.value).strip()
        elif fact.key in ("date_of_birth", "dob", "birth_date", "birthday"):
            parsed_dob = parse_flexible_date(fact.value)
            if parsed_dob is not None:
                profile.date_of_birth = parsed_dob
                profile.zodiac = compute_zodiac(profile.date_of_birth)
        elif fact.key in ("birth_place", "birthplace", "place_of_birth"):
            profile.birth_place = str(fact.value).strip()
        elif fact.key in ("preferred_language", "language"):
            profile.preferred_language = str(fact.value).strip()
        if profile.date_of_birth is not None and profile.zodiac is None:
            profile.zodiac = compute_zodiac(profile.date_of_birth)

    def _fallback_response(self, profile: Optional[UserProfile], facts: list[MemoryFact]) -> str:
        greeting = f"Namaste {profile.name}" if (profile and profile.name) else "Namaste seeker"
        sign_note = f" Reflecting on your {profile.zodiac} energy," if (profile and profile.zodiac) else ""
        if facts:
            context_summary = "; ".join(f"{f.key}: {f.value}" for f in facts[:2])
            return (
                f"{greeting}.{sign_note} I am temporarily experiencing a communication delay with the astrological oracle, "
                f"but I remember your stored focus ({context_summary}). "
                f"How may I support your journey while full connectivity restores?"
            )
        return (
            f"{greeting}.{sign_note} I am experiencing a brief communication delay with the astrological oracle. "
            f"Please share your inquiry again in a moment."
        )
