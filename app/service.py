"""Operazioni sul database: impostazioni, gironi, calendario, tabelloni, punteggi."""
import random
from datetime import datetime, timedelta

from . import tournament as T

TIME_FMT = "%Y-%m-%d %H:%M"

MATCH_SELECT = """
SELECT m.*, t1.name AS team1_name, t2.name AS team2_name, g.name AS group_name
FROM matches m
LEFT JOIN teams t1 ON t1.id = m.team1_id
LEFT JOIN teams t2 ON t2.id = m.team2_id
LEFT JOIN groups g ON g.id = m.group_id
"""


class TournamentError(Exception):
    """Errore mostrabile all'utente."""


# ------------------------------------------------------------ impostazioni

def get_setting(db, key, default=""):
    row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def get_int(db, key, default):
    try:
        return int(get_setting(db, key, default))
    except (TypeError, ValueError):
        return default


def set_setting(db, key, value):
    db.execute("INSERT INTO settings(key, value) VALUES (?, ?) "
               "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, str(value)))


def parse_start(db):
    raw = get_setting(db, "start_time").strip().replace("T", " ")
    try:
        return datetime.strptime(raw, TIME_FMT)
    except ValueError:
        return None


# ------------------------------------------------------------------ fasi

def tournament_phase(db):
    if db.execute("SELECT 1 FROM matches WHERE phase IN ('main','cons') LIMIT 1").fetchone():
        return "knockout"
    if db.execute("SELECT 1 FROM matches WHERE phase = 'group' LIMIT 1").fetchone():
        return "groups"
    if db.execute("SELECT 1 FROM groups LIMIT 1").fetchone():
        return "drawn"
    return "registration"


PHASE_LABELS = {
    "registration": "Iscrizioni",
    "drawn": "Gironi sorteggiati",
    "groups": "Fase a gironi",
    "knockout": "Fase finale",
}


def started_matches(db, phases):
    q = ",".join("?" * len(phases))
    return db.execute(
        "SELECT COUNT(*) FROM matches WHERE phase IN (%s) AND status != 'scheduled'" % q,
        phases).fetchone()[0]


# ----------------------------------------------------------------- squadre

def cert_state(player):
    if player["cert_ok"]:
        return "ok"
    return "uploaded" if player["cert_file"] else "missing"


def teams_with_players(db, where="1=1", params=()):
    teams = [dict(t) for t in db.execute(
        "SELECT t.*, u.email, g.name AS group_name FROM teams t "
        "LEFT JOIN users u ON u.id = t.user_id LEFT JOIN groups g ON g.id = t.group_id "
        "WHERE %s ORDER BY t.name" % where, params)]
    for t in teams:
        t["players"] = [dict(p, cert=cert_state(p)) for p in db.execute(
            "SELECT * FROM players WHERE team_id = ? ORDER BY id", (t["id"],))]
        t["certs_ok"] = sum(1 for p in t["players"] if p["cert"] == "ok")
        t["certs_missing"] = sum(1 for p in t["players"] if p["cert"] != "ok")
    return teams


# ------------------------------------------------------------------ gironi

def draw_groups(db, n_groups=None):
    if db.execute("SELECT 1 FROM matches LIMIT 1").fetchone():
        raise TournamentError("Il calendario esiste già: eliminalo prima di rifare il sorteggio.")
    ids = [r["id"] for r in db.execute("SELECT id FROM teams WHERE status = 'confirmed'")]
    if len(ids) < 2:
        raise TournamentError("Servono almeno 2 squadre confermate.")
    try:
        sizes = T.group_sizes(len(ids), n_groups)
    except ValueError as e:
        raise TournamentError(str(e))
    random.shuffle(ids)
    db.execute("UPDATE teams SET group_id = NULL")
    db.execute("DELETE FROM groups")
    pos = 0
    for gi, size in enumerate(sizes):
        gid = db.execute("INSERT INTO groups(name) VALUES (?)", (T.group_name(gi),)).lastrowid
        for tid in ids[pos:pos + size]:
            db.execute("UPDATE teams SET group_id = ? WHERE id = ?", (gid, tid))
        pos += size


def move_team(db, team_id, group_id):
    if db.execute("SELECT 1 FROM matches LIMIT 1").fetchone():
        raise TournamentError("Il calendario esiste già: non si possono spostare squadre.")
    db.execute("UPDATE teams SET group_id = ? WHERE id = ? AND status = 'confirmed'",
               (group_id, team_id))


def _next_seq(db):
    return (db.execute("SELECT COALESCE(MAX(seq), 0) FROM matches").fetchone()[0]) + 1


def generate_group_matches(db):
    if db.execute("SELECT 1 FROM matches LIMIT 1").fetchone():
        raise TournamentError("Calendario dei gironi già generato.")
    groups = db.execute("SELECT id FROM groups ORDER BY id").fetchall()
    if not groups:
        raise TournamentError("Sorteggia prima i gironi.")
    per_group = {}
    for g in groups:
        ids = [r["id"] for r in db.execute(
            "SELECT id FROM teams WHERE group_id = ? ORDER BY id", (g["id"],))]
        if len(ids) < 2:
            raise TournamentError("Ogni girone deve avere almeno 2 squadre.")
        per_group[g["id"]] = T.round_robin(ids)
    n_rounds = max(len(r) for r in per_group.values())
    batches = []
    for r in range(n_rounds):
        batch = [(gid, r, a, b) for gid, rounds in per_group.items()
                 if r < len(rounds) for a, b in rounds[r]]
        if batch:
            batches.append(batch)
    _insert_scheduled(db, batches, parse_start(db))


def _insert_scheduled(db, batches, start):
    minutes = get_int(db, "match_minutes", 20)
    courts = max(1, get_int(db, "courts", 1))
    seq = _next_seq(db)
    for (gid, r, a, b), court, t in T.assign_slots(batches, start, minutes, courts):
        db.execute(
            "INSERT INTO matches(phase, group_id, round, round_label, team1_id, team2_id,"
            " court, start_time, seq) VALUES ('group', ?, ?, ?, ?, ?, ?, ?, ?)",
            (gid, r, "Giornata %d" % (r + 1), a, b, court,
             t.strftime(TIME_FMT) if t else None, seq))
        seq += 1


def delete_group_matches(db):
    if db.execute("SELECT 1 FROM matches WHERE phase IN ('main','cons')").fetchone():
        raise TournamentError("Elimina prima la fase finale.")
    if started_matches(db, ["group"]):
        raise TournamentError("Alcune partite sono già iniziate: non si può eliminare il calendario.")
    db.execute("DELETE FROM matches WHERE phase = 'group'")


def group_data(db):
    """Per ogni girone: squadre in classifica + partite."""
    out = []
    for g in db.execute("SELECT * FROM groups ORDER BY id"):
        teams = db.execute("SELECT id, name FROM teams WHERE group_id = ?", (g["id"],)).fetchall()
        names = {t["id"]: t["name"] for t in teams}
        matches = [dict(m) for m in db.execute(
            MATCH_SELECT + " WHERE m.phase = 'group' AND m.group_id = ? ORDER BY m.seq", (g["id"],))]
        finished = [m for m in matches if m["status"] == "finished"]
        out.append(dict(id=g["id"], name=g["name"],
                        standings=T.standings(list(names), finished, names),
                        matches=matches))
    return out


# --------------------------------------------------------------- fase finale

def group_stage_complete(db):
    row = db.execute("SELECT COUNT(*) AS n, SUM(status = 'finished') AS f "
                     "FROM matches WHERE phase = 'group'").fetchone()
    return row["n"] > 0 and row["n"] == row["f"]


def overall_ranking(db):
    rows = []
    for g in group_data(db):
        rows.extend(g["standings"])
    rows.sort(key=T.overall_sort_key)
    return rows


def generate_knockout(db, main_size=None, ko_start=None):
    if tournament_phase(db) == "knockout":
        raise TournamentError("La fase finale è già stata generata.")
    if not group_stage_complete(db):
        raise TournamentError("Concludi tutte le partite dei gironi prima di generare la fase finale.")
    ranking = [r["team_id"] for r in overall_ranking(db)]
    n = len(ranking)
    if n < 4:
        raise TournamentError("Servono almeno 4 squadre per due tabelloni.")
    main_size = main_size or (n + 1) // 2
    if not 2 <= main_size <= n - 2:
        raise TournamentError("Ogni tabellone deve avere almeno 2 squadre.")
    group_of = {r["team_id"]: gid for gid, r in
                ((g["id"], r) for g in group_data(db) for r in g["standings"])}
    brackets = {phase: T.avoid_same_group(T.build_bracket(teams), group_of)
                for phase, teams in (("main", ranking[:main_size]), ("cons", ranking[main_size:]))}

    minutes = get_int(db, "match_minutes", 20)
    courts = max(1, get_int(db, "courts", 1))
    if ko_start is None:
        last = db.execute("SELECT MAX(start_time) FROM matches WHERE start_time IS NOT NULL").fetchone()[0]
        if last:
            ko_start = datetime.strptime(last, TIME_FMT) + timedelta(minutes=minutes)

    # inserimento a ritroso per conoscere gli id dei turni successivi
    ids = {}
    for phase, bracket in brackets.items():
        for m in sorted(bracket, key=lambda x: (-x["r"], x["i"])):
            nxt = ids.get((phase, ) + m["next"]) if m["next"] else None
            lnx = ids.get((phase, ) + m["loser_next"]) if m.get("loser_next") else None
            ids[(phase, m["r"], m["i"])] = db.execute(
                "INSERT INTO matches(phase, round, round_label, team1_id, team2_id,"
                " next_match_id, next_slot, loser_next_match_id, loser_next_slot)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (phase, m["r"], m["label"], m["team1"], m["team2"],
                 nxt, m["slot"] if nxt else None,
                 lnx, m["loser_slot"] if lnx else None)).lastrowid

    # calendario: turno per turno, tabellone principale prima della consolazione
    n_rounds = max([m["r"] for b in brackets.values() for m in b] + [0]) + 1
    batches = []
    for r in range(n_rounds):
        batch = [ids[(p, m["r"], m["i"])] for p in ("main", "cons")
                 for m in sorted(brackets[p], key=lambda x: not x.get("third"))
                 if m["r"] == r]
        if batch:
            batches.append(batch)
    seq = _next_seq(db)
    for mid, court, t in T.assign_slots(batches, ko_start, minutes, courts):
        db.execute("UPDATE matches SET court = ?, start_time = ?, seq = ? WHERE id = ?",
                   (court, t.strftime(TIME_FMT) if t else None, seq, mid))
        seq += 1


def delete_knockout(db):
    if started_matches(db, ["main", "cons"]):
        raise TournamentError("Alcune partite della fase finale sono già iniziate.")
    db.execute("DELETE FROM matches WHERE phase IN ('main','cons')")


def bracket_data(db, phase):
    rows = [dict(m) for m in db.execute(
        MATCH_SELECT + " WHERE m.phase = ? ORDER BY m.round, m.id", (phase,))]
    rounds, third = {}, None
    for m in rows:
        if m["round_label"] == "Finale 3º posto":
            third = m
            continue
        rounds.setdefault(m["round"], dict(label=m["round_label"], matches=[]))["matches"].append(m)
    return dict(rounds=[rounds[k] for k in sorted(rounds)], third=third)


# ---------------------------------------------------------------- punteggi

def get_match(db, match_id):
    row = db.execute(MATCH_SELECT + " WHERE m.id = ?", (match_id,)).fetchone()
    return dict(row) if row else None


def _winner_slot(m):
    return m["team1_id"] if m["score1"] > m["score2"] else m["team2_id"]


def start_match(db, match_id):
    m = get_match(db, match_id)
    if not m:
        raise TournamentError("Partita inesistente.")
    if m["status"] != "scheduled":
        raise TournamentError("La partita è già iniziata.")
    if not m["team1_id"] or not m["team2_id"]:
        raise TournamentError("Le squadre di questa partita non sono ancora definite.")
    db.execute("UPDATE matches SET status = 'live', score1 = 0, score2 = 0 WHERE id = ?", (match_id,))


def add_points(db, match_id, team, delta):
    col = "score1" if team == 1 else "score2"
    cur = db.execute("UPDATE matches SET %s = MAX(0, %s + ?) WHERE id = ? AND status = 'live'"
                     % (col, col), (delta, match_id))
    if cur.rowcount == 0:
        raise TournamentError("La partita non è in corso.")


def set_score(db, match_id, s1, s2):
    cur = db.execute("UPDATE matches SET score1 = ?, score2 = ? WHERE id = ? AND status = 'live'",
                     (max(0, s1), max(0, s2), match_id))
    if cur.rowcount == 0:
        raise TournamentError("La partita non è in corso.")


def _targets(m):
    """(match_id, slot, "winner"|"loser") verso cui avanzano vincitore e perdente."""
    out = []
    if m["next_match_id"]:
        out.append((m["next_match_id"], m["next_slot"], "winner"))
    if m.get("loser_next_match_id"):
        out.append((m["loser_next_match_id"], m["loser_next_slot"], "loser"))
    return out


def _check_targets_untouched(db, m):
    for mid, _slot, _kind in _targets(m):
        if get_match(db, mid)["status"] != "scheduled":
            raise TournamentError("Il turno successivo è già iniziato.")


def _advance(db, m):
    winner = _winner_slot(m)
    loser = m["team2_id"] if winner == m["team1_id"] else m["team1_id"]
    for mid, slot, kind in _targets(m):
        col = "team1_id" if slot == 0 else "team2_id"
        db.execute("UPDATE matches SET %s = ? WHERE id = ?" % col,
                   (winner if kind == "winner" else loser, mid))


def finish_match(db, match_id):
    """Chiude la partita: da qui i punti entrano in classifica / il vincitore avanza."""
    m = get_match(db, match_id)
    if not m or m["status"] != "live":
        raise TournamentError("La partita non è in corso.")
    if m["score1"] == m["score2"]:
        raise TournamentError("Punteggio in parità: serve un vincitore (supplementare).")
    _check_targets_untouched(db, m)
    db.execute("UPDATE matches SET status = 'finished', finished_at = ? WHERE id = ?",
               (datetime.now().strftime(TIME_FMT), match_id))
    _advance(db, m)


def reopen_match(db, match_id):
    m = get_match(db, match_id)
    if not m or m["status"] != "finished":
        raise TournamentError("La partita non è conclusa.")
    _check_targets_untouched(db, m)
    for mid, slot, _kind in _targets(m):
        col = "team1_id" if slot == 0 else "team2_id"
        db.execute("UPDATE matches SET %s = NULL WHERE id = ?" % col, (mid,))
    db.execute("UPDATE matches SET status = 'live', finished_at = NULL WHERE id = ?", (match_id,))
