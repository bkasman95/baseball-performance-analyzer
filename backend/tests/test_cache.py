import pandas as pd

from app.data import cache


def test_read_through_cache_writes_then_reads():
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        return pd.DataFrame({"a": [1, 2, 3]})

    df1 = cache.read_through_cache("unit_test:key1", fetch)
    df2 = cache.read_through_cache("unit_test:key1", fetch)

    assert calls["n"] == 1, "second call should hit the cache"
    assert df1.equals(df2)
    assert list(df1["a"]) == [1, 2, 3]


def test_force_refresh_bypasses_cache():
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        return pd.DataFrame({"a": [calls["n"]]})

    cache.read_through_cache("unit_test:key2", fetch)
    cache.read_through_cache("unit_test:key2", fetch, force_refresh=True)

    assert calls["n"] == 2


def test_invalidate_removes_matching_entries():
    cache.read_through_cache("prefix:a", lambda: pd.DataFrame({"x": [1]}))
    cache.read_through_cache("prefix:b", lambda: pd.DataFrame({"x": [2]}))
    cache.read_through_cache("other:c", lambda: pd.DataFrame({"x": [3]}))

    removed = cache.invalidate("prefix:")
    assert removed == 2
    assert cache.cache_lookup("prefix:a") is None
    assert cache.cache_lookup("other:c") is not None
