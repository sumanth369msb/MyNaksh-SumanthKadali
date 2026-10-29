from app.core import config
from app.core.exceptions import GraphError


def create_graph_store():
    settings = getattr(config, "settings", None)
    if settings is None:
        from app.core.config import Settings
        settings = Settings(_env_file=".env")
    backend = settings.graph_backend.lower()
    if backend == "neo4j":
        from app.brain.neo4j_store import Neo4jGraphStore

        return Neo4jGraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
    if backend == "memory":
        from app.brain.store import InMemoryGraphStore

        return InMemoryGraphStore()
    raise GraphError(f"Unknown graph backend: {backend}")
