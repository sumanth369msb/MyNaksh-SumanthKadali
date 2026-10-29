from app.core.config import settings
from app.core.exceptions import GraphError


def create_graph_store():
    backend = settings.graph_backend.lower()
    if backend == "neo4j":
        from app.brain.neo4j_store import Neo4jGraphStore

        return Neo4jGraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
    if backend == "memory":
        from app.brain.store import InMemoryGraphStore

        return InMemoryGraphStore()
    raise GraphError(f"Unknown graph backend: {backend}")
