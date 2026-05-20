"""Offline-safe tests for the player module: network calls are stubbed."""

import pandas as pd

from app.data import players


def _fake_register() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "key_mlbam": [605141, 660271, 545361, 700000],
            "key_fangraphs": [13510, 19755, 10155, None],
            "name_first": ["Mookie", "Shohei", "Mike", "Test"],
            "name_last":  ["Betts", "Ohtani", "Trout", "Rookie"],
            "mlb_played_first": [2014, 2018, 2011, 2025],
            "mlb_played_last":  [2025, 2025, 2025, 2025],
        }
    )


def test_search_players_ranks_exact_first(monkeypatch):
    monkeypatch.setattr(players, "_fetch_name_table", _fake_register)
    monkeypatch.setattr(players, "_attach_role", lambda p: p)  # skip role detection

    results = players.search_players("ohtani", limit=3)
    assert results, "should return at least one match"
    assert results[0].last_name == "Ohtani"


def test_search_players_two_word_query(monkeypatch):
    monkeypatch.setattr(players, "_fetch_name_table", _fake_register)
    monkeypatch.setattr(players, "_attach_role", lambda p: p)

    results = players.search_players("mookie betts", limit=3)
    assert results[0].full_name == "Mookie Betts"


def test_search_returns_empty_on_short_query(monkeypatch):
    monkeypatch.setattr(players, "_fetch_name_table", _fake_register)
    assert players.search_players("a") == []
