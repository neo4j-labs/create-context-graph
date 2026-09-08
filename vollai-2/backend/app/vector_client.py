"""Vector search client."""

from __future__ import annotations

import logging

from app.context_graph_client import execute_cypher

logger = logging.getLogger(__name__)


async def create_vector_index(
    index_name: str = "entity_embeddings",
    label: str = "Entity",
    property_name: str = "embedding",
    dimensions: int = 1536,
) -> None:
    """Create a vector index on a label/property."""
    try:
        await execute_cypher(f"""
            CREATE VECTOR INDEX {index_name} IF NOT EXISTS
            FOR (n:{label})
            ON (n.{property_name})
            OPTIONS {{
                indexConfig: {{
                    `vector.dimensions`: {dimensions},
                    `vector.similarity_function`: 'cosine'
                }}
            }}
        """)
        logger.info("Vector index '%s' created/verified", index_name)
    except Exception as e:
        logger.warning("Failed to create vector index '%s': %s", index_name, e)


async def vector_search(
    query_embedding: list[float],
    index_name: str = "entity_embeddings",
    top_k: int = 10,
) -> list[dict]:
    """Search for similar entities using vector index."""
    result = await execute_cypher(
        f"""
        CALL db.index.vector.queryNodes('{index_name}', $topK, $embedding)
        YIELD node, score
        RETURN node.name AS name, labels(node) AS labels, score
        ORDER BY score DESC
        """,
        {"embedding": query_embedding, "topK": top_k},
    )
    return result


async def hybrid_search(
    query: str,
    query_embedding: list[float] | None = None,
    label: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Hybrid search combining text matching and vector similarity."""
    if query_embedding:
        result = await execute_cypher(
            """
            CALL db.index.vector.queryNodes('entity_embeddings', $limit, $embedding)
            YIELD node, score AS vector_score
            WHERE ($label IS NULL OR $label IN labels(node))
            WITH node, vector_score
            OPTIONAL MATCH (node)-[r]-(related)
            RETURN node.name AS name, labels(node) AS labels,
                   vector_score, type(r) AS rel_type,
                   related.name AS related_name
            LIMIT $limit
            """,
            {"embedding": query_embedding, "label": label, "limit": limit},
        )
    else:
        result = await execute_cypher(
            """
            MATCH (node)
            WHERE ($label IS NULL OR $label IN labels(node))
              AND (toLower(node.name) CONTAINS toLower($query)
                   OR toLower(coalesce(node.description, '')) CONTAINS toLower($query))
            OPTIONAL MATCH (node)-[r]-(related)
            RETURN node.name AS name, labels(node) AS labels,
                   1.0 AS vector_score, type(r) AS rel_type,
                   related.name AS related_name
            LIMIT $limit
            """,
            {"query": query, "label": label, "limit": limit},
        )
    return result
