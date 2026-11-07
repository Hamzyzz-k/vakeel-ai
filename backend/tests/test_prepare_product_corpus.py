from types import SimpleNamespace

import pytest

from app.ingest import prepare_product_corpus as prep
from app.legal.statute_catalog import INGESTIBLE_STATUTES


def test_every_ingestible_statute_is_bundled_as_a_pdf():
    for spec in INGESTIBLE_STATUTES:
        bundled = prep.BUNDLED_STATUTES_DIR / spec.filename
        assert bundled.exists(), f"{spec.filename} is not bundled"
        assert bundled.read_bytes()[:5] == b"%PDF-"


def test_bundled_copy_is_used_without_network(tmp_path, monkeypatch):
    bundled_dir = tmp_path / "bundled"
    bundled_dir.mkdir()
    (bundled_dir / "act.pdf").write_bytes(b"%PDF-1.7 bundled")
    monkeypatch.setattr(prep, "BUNDLED_STATUTES_DIR", bundled_dir)
    monkeypatch.setattr(prep, "STATUTES_DIR", tmp_path / "raw")

    def no_network(*args, **kwargs):
        raise AssertionError("downloaded although a bundled copy exists")

    monkeypatch.setattr(prep.httpx, "stream", no_network)
    spec = SimpleNamespace(key="act", filename="act.pdf", source_url="https://example.invalid/act.pdf")
    path = prep.download_statute(spec)
    assert path.read_bytes() == b"%PDF-1.7 bundled"


def test_missing_source_url_still_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(prep, "STATUTES_DIR", tmp_path / "raw")
    with pytest.raises(ValueError):
        prep.download_statute(SimpleNamespace(key="x", filename="x.pdf", source_url=""))
