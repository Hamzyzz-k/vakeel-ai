"""
Precedent-map endpoint (spec section 61). Reads from the citation graph
built over corpus='eval' -- currently the only corpus with extracted
citation edges, since the product corpus has no judgments yet and so
nothing for the extractor to find there. This endpoint exists to
demonstrate the graph functioning against real, not synthetic, data; the
same app.pipeline.citation_graph functions run inside the chat pipeline
for corpus='product' the moment that corpus has judgments too.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.chat import _db_lock, _get_repo
from app.pipeline.citation_graph import build_citation_graph, build_precedent_map

router = APIRouter(prefix="/api/v1", tags=["research"])


class PrecedentEdgeOut(BaseModel):
    relationship: str
    direction: str  # "incoming" | "outgoing"
    other_id: str
    other_title: str | None = None


class PrecedentMapOut(BaseModel):
    source_id: str
    title: str
    edges: list[PrecedentEdgeOut]


@router.get("/precedent-map/{source_id:path}", response_model=PrecedentMapOut)
def precedent_map(source_id: str) -> PrecedentMapOut:
    with _db_lock:  # see app/api/chat.py's _db_lock docstring
        repo = _get_repo()
        if repo.get_source(source_id) is None:
            raise HTTPException(status_code=404, detail=f"No source with id {source_id!r}")

        graph = build_citation_graph(repo)
        nodes = build_precedent_map(repo, graph, source_id)
        node = nodes[0]

        edges_out = []
        for relationship, direction, other_id in node.edges:
            other = repo.get_source(other_id)
            edges_out.append(PrecedentEdgeOut(
                relationship=relationship, direction=direction, other_id=other_id,
                other_title=other["title"] if other else None,
            ))

    return PrecedentMapOut(source_id=node.source_id, title=node.title, edges=edges_out)
