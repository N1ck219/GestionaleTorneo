import pytest
from app import tournament as T


@pytest.mark.parametrize("n,exp", [(4, [4]), (5, [5]), (6, [3, 3]), (7, [4, 3]), (8, [4, 4]),
                                   (9, [3, 3, 3]), (10, [4, 3, 3]), (13, [4, 3, 3, 3]), (17, [4, 4, 3, 3, 3])])
def test_group_sizes(n, exp):
    assert T.group_sizes(n) == exp


def test_round_robin_everyone_plays_everyone_once():
    for n in (3, 4, 5):
        rounds = T.round_robin(range(n))
        pairs = [frozenset(p) for r in rounds for p in r]
        assert len(pairs) == len(set(pairs)) == n * (n - 1) // 2
        for r in rounds:
            teams = [t for p in r for t in p]
            assert len(teams) == len(set(teams))


def test_standings_tiebreak_by_mini_league_diff():
    ms = [dict(team1_id=1, team2_id=2, score1=10, score2=8),
          dict(team1_id=2, team2_id=3, score1=10, score2=5),
          dict(team1_id=3, team2_id=1, score1=21, score2=2)]
    rows = T.standings([1, 2, 3], ms, {1: "A", 2: "B", 3: "C"})
    assert [r["team_id"] for r in rows] == [3, 2, 1]
    assert all(r["pts"] == 2 for r in rows)


def test_standings_head_to_head_two_way():
    ms = [dict(team1_id=1, team2_id=2, score1=10, score2=8),   # 1 batte 2
          dict(team1_id=2, team2_id=3, score1=21, score2=2),
          dict(team1_id=3, team2_id=1, score1=10, score2=9)]
    # 1: 1V 1P, 2: 1V 1P, 3: 1V 1P -> tutti pari; scontro diretto non basta, diff avulsa decide
    rows = T.standings([1, 2, 3], ms)
    assert len(rows) == 3


def test_win_is_two_points_loss_zero():
    rows = T.standings([1, 2], [dict(team1_id=1, team2_id=2, score1=11, score2=4)])
    assert (rows[0]["team_id"], rows[0]["pts"], rows[1]["pts"]) == (1, 2, 0)


def test_seed_order():
    assert T.seed_order(8) == [1, 8, 4, 5, 2, 7, 3, 6]


@pytest.mark.parametrize("k", range(2, 17))
def test_bracket_is_consistent(k):
    teams = list(range(1, k + 1))
    b = T.build_bracket(teams)
    present = [t for m in b for t in (m["team1"], m["team2"]) if t]
    assert sorted(present) == teams          # ogni squadra entra una volta
    finals = [m for m in b if m["next"] is None and not m.get("third")]
    assert len(finals) == 1 and finals[0]["label"] == "Finale"
    for m in b:                              # i vincitori hanno sempre dove andare
        if m["next"]:
            assert any((n["r"], n["i"]) == m["next"] for n in b)


def test_best_seed_gets_bye():
    b = T.build_bracket([1, 2, 3, 4, 5])
    assert not any(1 in (m["team1"], m["team2"]) and m["r"] == 0 for m in b)
    assert 1 in [t for m in b if m["r"] == 1 for t in (m["team1"], m["team2"])]


def test_third_place_only_with_two_semifinals():
    assert not any(m.get("third") for m in T.build_bracket([1, 2]))
    assert not any(m.get("third") for m in T.build_bracket([1, 2, 3]))   # una sola semifinale reale
    for k in (4, 5, 6, 7, 8, 12):
        b = T.build_bracket(list(range(1, k + 1)))
        third = [m for m in b if m.get("third")]
        assert len(third) == 1
        feeders = [m for m in b if m.get("loser_next") == (third[0]["r"], third[0]["i"])]
        assert len(feeders) == 2 and {m["loser_slot"] for m in feeders} == {0, 1}


def test_avoid_same_group_swaps_when_possible():
    # 8 squadre in 2 gironi: le teste 1 e 8 sono dello stesso girone -> va corretto
    group_of = {1: "A", 2: "B", 3: "A", 4: "B", 5: "B", 6: "A", 7: "B", 8: "A"}
    b = T.build_bracket(list(range(1, 9)))
    assert any(group_of[m["team1"]] == group_of[m["team2"]] for m in b if m["r"] == 0)
    T.avoid_same_group(b, group_of)
    first = [m for m in b if m["r"] == 0]
    assert sorted(t for m in first for t in (m["team1"], m["team2"])) == list(range(1, 9))
    assert not any(group_of[m["team1"]] == group_of[m["team2"]] for m in first)
    assert [m["team1"] for m in first] == [1, 4, 2, 3]       # teste di serie alte invariate


def test_first_of_group_meets_last_of_other_group():
    b = T.build_bracket(list(range(1, 9)))
    pairs = {m["team1"]: m["team2"] for m in b if m["r"] == 0}
    assert pairs[1] == 8 and pairs[2] == 7
