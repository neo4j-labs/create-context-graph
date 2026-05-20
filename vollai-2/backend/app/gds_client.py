"""Graph Data Science client."""

from __future__ import annotations

from app.constants import COMMUNITY_GRAPH, PAGERANK_GRAPH, SIMILARITY_GRAPH, FASTRP_EMBEDDING_DIMENSIONS
from app.context_graph_client import execute_cypher

ENTITY_LABELS = ["Appearance", "Attack", "Block", "Chat", "ChatSession", "Dig", "Event", "Freeball", "GameInterruption", "League", "Match", "Player", "Rally", "Reception", "RotationState", "Serve", "Set", "SetAction", "Staff", "Stats", "Substitution", "Tactic", "Team", "XAFactor"]



async def check_gds_available() -> bool:
    """Check if GDS plugin is available."""
    try:
        result = await execute_cypher("RETURN gds.version() AS version")
        return bool(result)
    except Exception:
        return False


async def run_community_detection(label: str = "*") -> list[dict]:
    """Run Louvain community detection."""
    if label != "*" and label not in ENTITY_LABELS:
        return [{"error": f"Invalid label: {label}"}]
    try:
        await execute_cypher(f"""
            CALL gds.graph.project('{COMMUNITY_GRAPH}', '{label}', '*')
        """)
        result = await execute_cypher(f"""
            CALL gds.louvain.stream('{COMMUNITY_GRAPH}')
            YIELD nodeId, communityId
            RETURN gds.util.asNode(nodeId).name AS name, communityId
            ORDER BY communityId
        """)
        await execute_cypher(f"CALL gds.graph.drop('{COMMUNITY_GRAPH}')")
        return result
    except Exception as e:
        return [{"error": str(e)}]


async def run_pagerank(label: str = "*") -> list[dict]:
    """Run PageRank centrality."""
    if label != "*" and label not in ENTITY_LABELS:
        return [{"error": f"Invalid label: {label}"}]
    try:
        await execute_cypher(f"""
            CALL gds.graph.project('{PAGERANK_GRAPH}', '{label}', '*')
        """)
        result = await execute_cypher(f"""
            CALL gds.pageRank.stream('{PAGERANK_GRAPH}')
            YIELD nodeId, score
            RETURN gds.util.asNode(nodeId).name AS name, score
            ORDER BY score DESC
            LIMIT 20
        """)
        await execute_cypher(f"CALL gds.graph.drop('{PAGERANK_GRAPH}')")
        return result
    except Exception as e:
        return [{"error": str(e)}]


async def run_similarity(label: str = "*") -> list[dict]:
    """Run KNN similarity using FastRP embeddings."""
    if label != "*" and label not in ENTITY_LABELS:
        return [{"error": f"Invalid label: {label}"}]
    try:
        await execute_cypher(f"""
            CALL gds.graph.project('{SIMILARITY_GRAPH}', '{label}', '*')
        """)
        await execute_cypher(f"""
            CALL gds.fastRP.mutate('{SIMILARITY_GRAPH}', {{
                embeddingDimension: {FASTRP_EMBEDDING_DIMENSIONS},
                mutateProperty: 'fastrp_embedding'
            }})
        """)
        result = await execute_cypher(f"""
            CALL gds.knn.stream('{SIMILARITY_GRAPH}', {{
                topK: 5,
                nodeProperties: ['fastrp_embedding']
            }})
            YIELD node1, node2, similarity
            RETURN gds.util.asNode(node1).name AS entity1,
                   gds.util.asNode(node2).name AS entity2,
                   similarity
            ORDER BY similarity DESC
            LIMIT 20
        """)
        await execute_cypher(f"CALL gds.graph.drop('{SIMILARITY_GRAPH}')")
        return result
    except Exception as e:
        return [{"error": str(e)}]
