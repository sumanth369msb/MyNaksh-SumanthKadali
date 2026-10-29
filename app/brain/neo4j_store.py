import json
from datetime import datetime, timezone
from typing import Any, Optional

from neo4j import AsyncGraphDatabase

from app.brain.models import MemoryFact
from app.core.exceptions import GraphError
from app.profile.models import UserProfile


class Neo4jGraphStore:
    def __init__(self, uri: str, user: str, password: str):
        self._driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    async def connect(self) -> None:
        try:
            await self._driver.verify_connectivity()
        except Exception as exc:
            raise GraphError(f"Neo4j connection failed: {exc}")

    async def close(self) -> None:
        await self._driver.close()

    async def upsert_user(self, profile: UserProfile) -> None:
        try:
            async with self._driver.session() as session:
                await session.run(
                    "MERGE (u:User {id: $id}) SET u += $props",
                    id=profile.user_id,
                    props=profile.model_dump(mode="json", exclude_none=True),
                )
        except Exception as exc:
            raise GraphError(str(exc))

    async def get_user(self, user_id: str) -> Optional[UserProfile]:
        try:
            async with self._driver.session() as session:
                result = await session.run(
                    "MATCH (u:User {id: $id}) RETURN u", id=user_id
                )
                record = await result.single()
                if record is None:
                    return None
                data = dict(record["u"])
                data.setdefault("user_id", user_id)
                return UserProfile(**data)
        except Exception as exc:
            raise GraphError(str(exc))

    async def upsert_fact(self, fact: MemoryFact) -> MemoryFact:
        fact_id = fact.id or f"{fact.user_id}:{fact.type}:{fact.key}"
        fact.id = fact_id
        now = datetime.now(timezone.utc).isoformat()
        try:
            async with self._driver.session() as session:
                await session.run(
                    """
                    MERGE (u:User {id: $user_id})
                    MERGE (f:Fact {id: $fact_id})
                    ON CREATE SET f.created_at = $created_at
                    SET f.type = $type,
                        f.key = $key,
                        f.value = $value,
                        f.relation = $relation,
                        f.confidence = $confidence,
                        f.source = $source,
                        f.metadata = $metadata,
                        f.updated_at = $updated_at
                    MERGE (u)-[:HAS_FACT]->(f)
                    """,
                    user_id=fact.user_id,
                    fact_id=fact_id,
                    type=fact.type,
                    key=fact.key,
                    value=fact.value,
                    relation=fact.relation,
                    confidence=fact.confidence,
                    source=fact.source,
                    metadata=json.dumps(fact.metadata),
                    created_at=fact.created_at.isoformat(),
                    updated_at=now,
                )
            fact.updated_at = datetime.fromisoformat(now)
            return fact
        except Exception as exc:
            raise GraphError(str(exc))

    async def get_facts(
        self, user_id: str, types: Optional[list[str]] = None, limit: int = 100
    ) -> list[MemoryFact]:
        try:
            async with self._driver.session() as session:
                if types:
                    result = await session.run(
                        "MATCH (u:User {id: $uid})-[:HAS_FACT]->(f:Fact) "
                        "WHERE f.type IN $types RETURN f ORDER BY f.updated_at DESC LIMIT $limit",
                        uid=user_id,
                        types=types,
                        limit=limit,
                    )
                else:
                    result = await session.run(
                        "MATCH (u:User {id: $uid})-[:HAS_FACT]->(f:Fact) "
                        "RETURN f ORDER BY f.updated_at DESC LIMIT $limit",
                        uid=user_id,
                        limit=limit,
                    )
                facts = []
                async for record in result:
                    f = dict(record["f"])
                    f["metadata"] = json.loads(f.get("metadata") or "{}")
                    f["user_id"] = user_id
                    facts.append(MemoryFact(**f))
                return facts
        except Exception as exc:
            raise GraphError(str(exc))

    async def search_facts(
        self, user_id: str, query: str, types: Optional[list[str]] = None, limit: int = 100
    ) -> list[MemoryFact]:
        facts = await self.get_facts(user_id, types=types, limit=1000)
        q = query.lower()
        tokens = set(q.split())
        scored = []
        for fact in facts:
            text = f"{fact.type} {fact.key} {fact.value} {fact.metadata}".lower()
            score = sum(1 for t in tokens if t in text)
            if q and q in text:
                score += 2
            scored.append((score, fact))
        scored.sort(key=lambda x: (x[0], x[1].updated_at.timestamp()), reverse=True)
        if not scored:
            return []
        top = [f for score, f in scored if score > 0]
        return (top or [f for _, f in scored])[:limit]

    async def delete_fact(self, user_id: str, fact_id: str) -> bool:
        try:
            async with self._driver.session() as session:
                result = await session.run(
                    "MATCH (u:User {id: $uid})-[:HAS_FACT]->(f:Fact {id: $fid}) "
                    "DETACH DELETE f RETURN count(f) AS c",
                    uid=user_id,
                    fid=fact_id,
                )
                record = await result.single()
                return bool(record and record["c"] > 0)
        except Exception as exc:
            raise GraphError(str(exc))

    async def clear_user(self, user_id: str) -> None:
        try:
            async with self._driver.session() as session:
                await session.run(
                    """
                    MATCH (u:User {id: $uid})
                    OPTIONAL MATCH (u)-[:HAS_FACT]->(f:Fact)
                    DETACH DELETE u, f
                    """,
                    uid=user_id,
                )
        except Exception as exc:
            raise GraphError(str(exc))
