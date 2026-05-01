from __future__ import annotations

from services.etl.enrich_players import enrich_player_rows


def test_enrich_player_rows_updates_names_and_hands(monkeypatch) -> None:
    rows = [
        {
            "player_id": "pitcher_663978",
            "mlbam_id": 663978,
            "name": "Crawford, J.P.",
            "bats": None,
            "throws": "R",
            "primary_role": "pitcher",
        },
        {
            "player_id": "hitter_694384",
            "mlbam_id": 694384,
            "name": "Schanuel, Nolan",
            "bats": "L",
            "throws": None,
            "primary_role": "hitter",
        },
    ]

    def fake_fetch_people(person_ids: list[int]):
        assert person_ids == [663978, 694384]
        return {
            663978: {
                "id": 663978,
                "fullName": "Player Pitcher",
                "batSide": {"code": "R"},
                "pitchHand": {"code": "L"},
            },
            694384: {
                "id": 694384,
                "fullName": "Player Hitter",
                "batSide": {"code": "L"},
                "pitchHand": {"code": "R"},
            },
        }

    monkeypatch.setattr("services.etl.enrich_players.fetch_people", fake_fetch_people)
    enriched = enrich_player_rows(rows, batch_size=50, pause_seconds=0.0)

    assert enriched[0]["name"] == "Player Pitcher"
    assert enriched[0]["throws"] == "L"
    assert enriched[1]["name"] == "Player Hitter"
    assert enriched[1]["bats"] == "L"
    assert enriched[1]["throws"] is None
