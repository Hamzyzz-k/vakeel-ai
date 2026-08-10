from app.corpus.repository import SQLiteCorpusRepository, LegalSource
from app.pipeline.citation_graph import (
    build_citation_graph, detect_conflicts, build_precedent_map, _stronger_authority,
)


def make_repo(tmp_path):
    return SQLiteCorpusRepository(str(tmp_path / "test.db"))


def add_source(repo, source_id, title, authority_level=3, date=None, bench_strength=None):
    repo.upsert_source(LegalSource(
        id=source_id, corpus="eval", source_type="JUDGMENT", title=title,
        full_text=title, authority_level=authority_level, date=date, bench_strength=bench_strength,
    ))


def add_citation(repo, source_id, cited_id, relationship):
    repo._conn().execute(
        "INSERT INTO citations (source_id, cited_source_id, relationship, confidence) VALUES (?, ?, ?, ?)",
        (source_id, cited_id, relationship, 1.0),
    )
    repo._conn().commit()


def test_build_citation_graph_loads_edges_with_relationship(tmp_path):
    repo = make_repo(tmp_path)
    add_source(repo, "a", "Case A")
    add_source(repo, "b", "Case B")
    add_citation(repo, "a", "b", "FOLLOWS")

    graph = build_citation_graph(repo)
    assert graph.has_edge("a", "b")
    assert graph["a"]["b"]["relationship"] == "FOLLOWS"


def test_detect_conflicts_finds_overrules_edge(tmp_path):
    repo = make_repo(tmp_path)
    add_source(repo, "old", "Old Case", authority_level=3, date="2010-01-01")
    add_source(repo, "new", "New Case", authority_level=3, date="2020-01-01")
    add_citation(repo, "new", "old", "OVERRULES")
    graph = build_citation_graph(repo)

    findings = detect_conflicts(repo, graph, ["old", "new"])

    assert len(findings) == 1
    assert findings[0].relationship == "OVERRULES"
    assert findings[0].stronger == "new"  # the overruling case wins outright


def test_detect_conflicts_ignores_plain_cites_edges(tmp_path):
    """A CITES edge is not a conflict -- only OVERRULES/DISTINGUISHES are."""
    repo = make_repo(tmp_path)
    add_source(repo, "a", "Case A")
    add_source(repo, "b", "Case B")
    add_citation(repo, "a", "b", "CITES")
    graph = build_citation_graph(repo)

    findings = detect_conflicts(repo, graph, ["a", "b"])
    assert findings == []


def test_stronger_authority_higher_court_wins_regardless_of_date(tmp_path):
    """Court hierarchy outranks date -- an older Supreme Court decision
    beats a newer High Court one."""
    repo = make_repo(tmp_path)
    add_source(repo, "sc", "SC Case", authority_level=3, date="2000-01-01")
    add_source(repo, "hc", "HC Case", authority_level=4, date="2023-01-01")

    assert _stronger_authority(repo, "sc", "hc") == "sc"
    assert _stronger_authority(repo, "hc", "sc") == "sc"


def test_stronger_authority_falls_back_to_date_when_same_court(tmp_path):
    repo = make_repo(tmp_path)
    add_source(repo, "old", "Old", authority_level=3, date="2010-01-01")
    add_source(repo, "new", "New", authority_level=3, date="2020-01-01")

    assert _stronger_authority(repo, "old", "new") == "new"


def test_stronger_authority_falls_back_to_bench_strength_when_same_court_and_date(tmp_path):
    repo = make_repo(tmp_path)
    add_source(repo, "small", "Small Bench", authority_level=3, date="2015-01-01", bench_strength=2)
    add_source(repo, "large", "Large Bench", authority_level=3, date="2015-01-01", bench_strength=5)

    assert _stronger_authority(repo, "small", "large") == "large"


def test_stronger_authority_returns_none_when_genuinely_indeterminate(tmp_path):
    repo = make_repo(tmp_path)
    add_source(repo, "a", "A", authority_level=3)
    add_source(repo, "b", "B", authority_level=3)

    assert _stronger_authority(repo, "a", "b") is None


def test_precedent_map_includes_incoming_and_outgoing_edges(tmp_path):
    repo = make_repo(tmp_path)
    add_source(repo, "center", "Center Case")
    add_source(repo, "cites_out", "Cites Out")
    add_source(repo, "cited_by", "Cited By")
    add_citation(repo, "center", "cites_out", "CITES")
    add_citation(repo, "cited_by", "center", "FOLLOWS")
    graph = build_citation_graph(repo)

    nodes = build_precedent_map(repo, graph, "center")

    assert len(nodes) == 1
    edges = nodes[0].edges
    assert ("CITES", "outgoing", "cites_out") in edges
    assert ("FOLLOWS", "incoming", "cited_by") in edges


def test_precedent_map_handles_source_with_no_edges(tmp_path):
    repo = make_repo(tmp_path)
    add_source(repo, "isolated", "Isolated Case")
    graph = build_citation_graph(repo)

    nodes = build_precedent_map(repo, graph, "isolated")
    assert nodes[0].edges == []
    assert nodes[0].title == "Isolated Case"
