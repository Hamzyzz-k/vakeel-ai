from app.llm.cache import LLMCache


def _age_all_rows(cache: LLMCache, days: int) -> None:
    cache._conn.execute("UPDATE llm_cache SET created_at = datetime('now', ?)", (f"-{days} days",))
    cache._conn.commit()


def test_cache_entries_expire_after_ttl(tmp_path):
    cache = LLMCache(str(tmp_path / "cache.db"), ttl_days=7)
    cache.put("groq", "m", "old question", "old answer")
    _age_all_rows(cache, 8)
    assert cache.get("groq", "m", "old question") is None

    cache.put("groq", "m", "new question", "new answer")
    assert cache.get("groq", "m", "new question") == "new answer"
    # Writing also deletes expired rows, so old answers don't linger on disk.
    assert cache.count() == 1


def test_cache_without_ttl_keeps_entries(tmp_path):
    cache = LLMCache(str(tmp_path / "cache.db"), ttl_days=0)
    cache.put("groq", "m", "question", "answer")
    _age_all_rows(cache, 400)
    assert cache.get("groq", "m", "question") == "answer"
