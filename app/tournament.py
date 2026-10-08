"""Logica pura del torneo (nessuna dipendenza da Flask o dal database)."""
from datetime import timedelta
from math import ceil, log2

WIN_POINTS = 2


# ---------------------------------------------------------------- gironi

def suggest_groups(n_teams):
    """Numero di gironi consigliato: 3 o 4 squadre per girone."""
    if n_teams < 6:
        return 1
    return ceil(n_teams / 4)


def group_sizes(n_teams, n_groups=None):
    """Dimensioni dei gironi, il più possibile bilanciate."""
    if n_teams < 2:
        raise ValueError("Servono almeno 2 squadre")
    g = n_groups or suggest_groups(n_teams)
    if g < 1 or g > n_teams // 2:
        raise ValueError("Numero di gironi non valido per %d squadre" % n_teams)
    base, rem = divmod(n_teams, g)
    return [base + 1] * rem + [base] * (g - rem)


def group_name(index):
    return "Girone " + chr(ord("A") + index) if index < 26 else "Girone %d" % (index + 1)


def round_robin(team_ids):
    """Girone all'italiana (metodo del cerchio). Ritorna una lista di giornate,
    ognuna lista di coppie (a, b)."""
    teams = list(team_ids)
    if len(teams) % 2:
        teams.append(None)
    n = len(teams)
    rounds = []
    for r in range(n - 1):
        pairs = []
        for i in range(n // 2):
            a, b = teams[i], teams[n - 1 - i]
            if a is not None and b is not None:
                pairs.append((a, b) if (r + i) % 2 == 0 else (b, a))
        rounds.append(pairs)
        teams = [teams[0]] + [teams[-1]] + teams[1:-1]
    return rounds


# ------------------------------------------------------------ classifica

def standings(team_ids, finished_matches, names=None):
    """Classifica di un girone.

    finished_matches: dict con team1_id, team2_id, score1, score2.
    Criteri: punti, scontri diretti / classifica avulsa tra le pari merito,
    differenza canestri, canestri fatti, nome.
    """
    names = names or {}
    rows = {
        t: dict(team_id=t, name=names.get(t, str(t)), played=0, wins=0, losses=0,
                pf=0, pa=0, diff=0, pts=0)
        for t in team_ids
    }
    valid = []
    for m in finished_matches:
        a, b = m["team1_id"], m["team2_id"]
        if a not in rows or b not in rows:
            continue
        valid.append(m)
        s1, s2 = m["score1"], m["score2"]
        for t, pf, pa in ((a, s1, s2), (b, s2, s1)):
            r = rows[t]
            r["played"] += 1
            r["pf"] += pf
            r["pa"] += pa
            if pf > pa:
                r["wins"] += 1
                r["pts"] += WIN_POINTS
            elif pf < pa:
                r["losses"] += 1
    for r in rows.values():
        r["diff"] = r["pf"] - r["pa"]

    ordered = sorted(rows.values(), key=lambda r: (-r["pts"], r["name"].lower()))
    result, i = [], 0
    while i < len(ordered):
        j = i
        while j < len(ordered) and ordered[j]["pts"] == ordered[i]["pts"]:
            j += 1
        bucket = ordered[i:j]
        if len(bucket) > 1:
            ids = {r["team_id"] for r in bucket}
            mini = {t: [0, 0] for t in ids}  # punti, differenza
            for m in valid:
                a, b = m["team1_id"], m["team2_id"]
                if a in ids and b in ids:
                    d = m["score1"] - m["score2"]
                    mini[a][1] += d
                    mini[b][1] -= d
                    if d > 0:
                        mini[a][0] += WIN_POINTS
                    elif d < 0:
                        mini[b][0] += WIN_POINTS
            bucket.sort(key=lambda r: (-mini[r["team_id"]][0], -mini[r["team_id"]][1],
                                       -r["diff"], -r["pf"], r["name"].lower()))
        result.extend(bucket)
        i = j
    for pos, r in enumerate(result, 1):
        r["position"] = pos
    return result


def overall_sort_key(row):
    """Per confrontare squadre di gironi diversi (anche di dimensione diversa):
    posizione nel girone, poi medie a partita."""
    played = row["played"] or 1
    return (row["position"], -row["pts"] / played, -row["diff"] / played,
            -row["pf"] / played, row["name"].lower())


# ------------------------------------------------------- tabelloni

def seed_order(size):
    """Ordine standard delle teste di serie nel tabellone (size potenza di 2)."""
    order = [1]
    m = 1
    while m < size:
        m *= 2
        order = [x for s in order for x in (s, m + 1 - s)]
    return order


def round_label(matches_in_round, round_index):
    return {1: "Finale", 2: "Semifinali", 4: "Quarti di finale",
            8: "Ottavi di finale"}.get(matches_in_round, "Turno %d" % (round_index + 1))


def build_bracket(seeded_teams):
    """Costruisce un tabellone a eliminazione diretta.

    seeded_teams: squadre ordinate dalla testa di serie 1 in poi.
    Le teste di serie migliori ricevono il bye se il numero non è una potenza di 2.
    Ritorna lista di dict: r, i, team1, team2, label, next (r, i) o None, slot.
    I match del primo turno con bye non vengono creati: la squadra è già
    inserita nel turno successivo.
    """
    k = len(seeded_teams)
    if k < 2:
        return []
    size = 1 << ceil(log2(k))
    n_rounds = int(log2(size))
    pos = seed_order(size)

    def team(seed):
        return seeded_teams[seed - 1] if seed <= k else None

    matches = {}
    for r in range(n_rounds):
        count = size >> (r + 1)
        for i in range(count):
            matches[(r, i)] = dict(
                r=r, i=i, team1=None, team2=None,
                label=round_label(count, r),
                next=(r + 1, i // 2) if r + 1 < n_rounds else None,
                slot=i % 2)
    for i in range(size // 2):
        t1, t2 = team(pos[2 * i]), team(pos[2 * i + 1])
        if t1 is not None and t2 is not None:
            matches[(0, i)]["team1"], matches[(0, i)]["team2"] = t1, t2
        else:  # bye
            winner = t1 if t1 is not None else t2
            nxt = matches.get((1, i // 2))
            del matches[(0, i)]
            if nxt is not None:
                nxt["team1" if i % 2 == 0 else "team2"] = winner
    # finale per il 3º posto: serve che entrambe le semifinali si giochino davvero
    if n_rounds >= 2 and (n_rounds - 2, 0) in matches and (n_rounds - 2, 1) in matches:
        last = n_rounds - 1
        matches[(last, 1)] = dict(r=last, i=1, team1=None, team2=None,
                                  label="Finale 3º posto", next=None, slot=0, third=True)
        for i in (0, 1):
            matches[(n_rounds - 2, i)]["loser_next"] = (last, 1)
            matches[(n_rounds - 2, i)]["loser_slot"] = i
    return sorted(matches.values(), key=lambda m: (m["r"], m["i"]))


def avoid_same_group(bracket, group_of):
    """Evita, dove possibile, che nel primo turno si incontrino squadre dello
    stesso girone: scambia la squadra con il seed più basso con quella di un'altra
    partita dello stesso turno (le teste di serie alte restano dove sono)."""
    ready = [m for m in bracket if m["team1"] is not None and m["team2"] is not None]

    def same(a, b):
        return group_of.get(a) is not None and group_of.get(a) == group_of.get(b)

    for m in ready:
        if not same(m["team1"], m["team2"]):
            continue
        others = sorted((n for n in ready if n is not m and n["r"] == m["r"]),
                        key=lambda n: abs(n["i"] - m["i"]))
        for n in others:
            if not same(m["team1"], n["team2"]) and not same(n["team1"], m["team2"]):
                m["team2"], n["team2"] = n["team2"], m["team2"]
                break
    return bracket


# ------------------------------------------------------ calendario

def assign_slots(batches, start, minutes, courts):
    """Distribuisce le partite su campi e orari. Ogni batch (giornata/turno)
    inizia su una nuova riga oraria. start può essere None (solo campo)."""
    out = []
    t = start
    for batch in batches:
        for i in range(0, len(batch), courts):
            for c, item in enumerate(batch[i:i + courts], 1):
                out.append((item, c, t))
            if t is not None:
                t = t + timedelta(minutes=minutes)
    return out
