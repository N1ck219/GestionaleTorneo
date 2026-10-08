import hmac
import os
import re
import secrets
import time
from datetime import datetime
from functools import wraps

from flask import (Blueprint, abort, flash, g, jsonify, redirect, render_template,
                   request, send_from_directory, session, url_for, Response)
from werkzeug.security import check_password_hash, generate_password_hash

from . import service as S
from .db import get_db
from .tournament import suggest_groups, group_sizes

bp = Blueprint("main", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAGIC = {b"%PDF": "pdf", b"\xff\xd8\xff": "jpg", b"\x89PNG": "png"}
_attempts = {}


# ------------------------------------------------------------ infrastruttura

def register_helpers(app):
    @app.before_request
    def load_user():
        g.user = None
        uid = session.get("uid")
        if uid:
            row = get_db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
            g.user = dict(row) if row else None
            if g.user is None:
                session.clear()

    @app.before_request
    def check_csrf():
        if request.method == "POST":
            sent = request.form.get("_csrf") or request.headers.get("X-CSRF-Token", "")
            token = session.get("csrf")
            if not token or not hmac.compare_digest(sent, token):
                abort(400, "Sessione scaduta: ricarica la pagina e riprova.")

    @app.after_request
    def headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("Content-Security-Policy",
                                "default-src 'self'; img-src 'self' data:; object-src 'none'; "
                                "frame-ancestors 'self'; base-uri 'self'; form-action 'self'")
        if request.is_secure or request.headers.get("X-Forwarded-Proto") == "https":
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        return resp

    @app.context_processor
    def inject():
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(24)
        db = get_db()
        return dict(
            user=g.get("user"), csrf=session["csrf"],
            t_name=S.get_setting(db, "tournament_name", "Torneo 3v3"),
            registration_open=S.get_setting(db, "registration_open") == "1")

    @app.template_filter("when")
    def when(value):
        if not value:
            return ""
        try:
            d = datetime.strptime(value, S.TIME_FMT)
        except ValueError:
            return value
        days = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]
        return "%s %02d/%02d %02d:%02d" % (days[d.weekday()], d.day, d.month, d.hour, d.minute)

    @app.template_filter("clock")
    def clock(value):
        return value[11:16] if value and len(value) >= 16 else ""

    @app.template_filter("match_title")
    def match_title(m):
        if m["phase"] == "group":
            return "%s · %s" % (m["group_name"], m["round_label"])
        prefix = "Fase finale" if m["phase"] == "main" else "Consolazione"
        return "%s · %s" % (prefix, m["round_label"])

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(413)
    def err(e):
        msg = {413: "File troppo grande (massimo 10 MB)."}.get(e.code, e.description)
        return render_template("error.html", code=e.code, message=msg), e.code


def roles_required(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if g.user is None:
                if request.path.startswith("/api/"):
                    return jsonify(error="Accesso richiesto"), 401
                return redirect(url_for("main.login"))
            if g.user["role"] not in roles:
                if request.path.startswith("/api/"):
                    return jsonify(error="Non autorizzato"), 403
                abort(403, "Non hai i permessi per questa pagina.")
            return fn(*a, **kw)
        return wrapper
    return deco


def home_for(user):
    return url_for({"boss": "main.admin_home", "scorer": "main.table_home",
                    "team": "main.team_home"}[user["role"]])


def my_team(db):
    row = db.execute("SELECT * FROM teams WHERE user_id = ?", (g.user["id"],)).fetchone()
    if not row:
        abort(404, "Nessuna squadra associata a questo account.")
    return dict(row)


def owned_player(db, player_id):
    p = db.execute("SELECT * FROM players WHERE id = ?", (player_id,)).fetchone()
    if not p:
        abort(404)
    if g.user["role"] != "boss":
        t = db.execute("SELECT user_id FROM teams WHERE id = ?", (p["team_id"],)).fetchone()
        if g.user["role"] != "team" or t["user_id"] != g.user["id"]:
            abort(403)
    return dict(p)


def parse_date(raw):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return None


def fail(msg, endpoint, **kw):
    flash(msg, "error")
    return redirect(url_for(endpoint, **kw))


# ----------------------------------------------------------------- pubblico

def live_context(db):
    live = [dict(m) for m in db.execute(S.MATCH_SELECT + " WHERE m.status = 'live' ORDER BY m.seq")]
    upcoming = [dict(m) for m in db.execute(
        S.MATCH_SELECT + " WHERE m.status = 'scheduled' AND m.team1_id IS NOT NULL "
        "AND m.team2_id IS NOT NULL ORDER BY m.seq LIMIT 8")]
    recent = [dict(m) for m in db.execute(
        S.MATCH_SELECT + " WHERE m.status = 'finished' ORDER BY m.finished_at DESC, m.id DESC LIMIT 8")]
    return dict(live=live, upcoming=upcoming, recent=recent)


@bp.route("/")
def home():
    db = get_db()
    return render_template("home.html", info=S.get_setting(db, "tournament_info"),
                           phase=S.PHASE_LABELS[S.tournament_phase(db)], **live_context(db))


@bp.route("/fragment/live")
def fragment_live():
    return render_template("_live.html", **live_context(get_db()))


@bp.route("/gironi")
def groups_page():
    return render_template("groups.html", groups=S.group_data(get_db()))


@bp.route("/fragment/gironi")
def fragment_groups():
    return render_template("_groups.html", groups=S.group_data(get_db()))


@bp.route("/tabellone")
def bracket_page():
    db = get_db()
    return render_template("bracket.html", main=S.bracket_data(db, "main"),
                           cons=S.bracket_data(db, "cons"))


@bp.route("/fragment/tabellone")
def fragment_bracket():
    db = get_db()
    return render_template("_bracket.html", main=S.bracket_data(db, "main"),
                           cons=S.bracket_data(db, "cons"))


@bp.route("/calendario")
def schedule_page():
    matches = [dict(m) for m in get_db().execute(S.MATCH_SELECT + " ORDER BY m.seq")]
    return render_template("schedule.html", matches=matches)


@bp.route("/squadre")
def teams_page():
    teams = S.teams_with_players(get_db(), "t.status = 'confirmed'")
    return render_template("teams.html", teams=teams)


@bp.route("/partita/<int:match_id>")
def match_page(match_id):
    m = S.get_match(get_db(), match_id)
    if not m:
        abort(404)
    return render_template("match.html", m=m)


@bp.route("/fragment/partita/<int:match_id>")
def fragment_match(match_id):
    m = S.get_match(get_db(), match_id)
    if not m:
        abort(404)
    return render_template("_scoreboard.html", m=m)


# ------------------------------------------------------------------- accesso

def throttled(key, limit=10):
    now = time.time()
    hits = [t for t in _attempts.get(key, []) if now - t < 300]
    _attempts[key] = hits
    return len(hits) >= limit


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        key = "%s|%s" % (request.remote_addr, email)
        if throttled(key):
            return fail("Troppi tentativi, riprova tra qualche minuto.", "main.login")
        row = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if row and check_password_hash(row["password_hash"], request.form.get("password", "")):
            csrf = session.get("csrf")
            session.clear()
            session["csrf"] = csrf or secrets.token_urlsafe(24)
            session["uid"] = row["id"]
            session.permanent = True
            return redirect(home_for(row))
        _attempts.setdefault(key, []).append(time.time())
        return fail("Email o password errati.", "main.login")
    if g.user:
        return redirect(home_for(g.user))
    return render_template("login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("main.home"))


@bp.route("/iscrizione", methods=["GET", "POST"])
def register():
    db = get_db()
    if S.get_setting(db, "registration_open") != "1":
        return render_template("register_closed.html")
    min_p = S.get_int(db, "min_players", 4)
    max_p = S.get_int(db, "max_players", 8)
    if request.method == "POST":
        rkey = "reg|%s" % request.remote_addr
        if throttled(rkey, 15):
            return fail("Troppe richieste, riprova tra qualche minuto.", "main.register")
        _attempts.setdefault(rkey, []).append(time.time())
        f = request.form
        team = f.get("team_name", "").strip()
        email = f.get("email", "").strip().lower()
        password = f.get("password", "")
        players = []
        for fn, ln, bd in zip(f.getlist("first_name"), f.getlist("last_name"), f.getlist("birth_date")):
            fn, ln = fn.strip(), ln.strip()
            if fn or ln:
                players.append((fn, ln, parse_date(bd)))
        err = None
        if not team or len(team) > 60:
            err = "Inserisci il nome della squadra (max 60 caratteri)."
        elif not EMAIL_RE.match(email):
            err = "Email non valida."
        elif len(password) < 8:
            err = "La password deve avere almeno 8 caratteri."
        elif any(not fn or not ln for fn, ln, _ in players):
            err = "Nome e cognome sono obbligatori per ogni giocatore."
        elif len(players) < min_p:
            err = "Servono almeno %d giocatori." % min_p
        elif len(players) > max_p:
            err = "Massimo %d giocatori per squadra." % max_p
        elif db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            err = "Esiste già un account con questa email."
        elif db.execute("SELECT 1 FROM teams WHERE name = ?", (team,)).fetchone():
            err = "Esiste già una squadra con questo nome."
        if err:
            flash(err, "error")
            return render_template("register.html", min_p=min_p, max_p=max_p, form=f,
                                   players=players or [("", "", None)] * min_p), 400
        uid = db.execute("INSERT INTO users(email, password_hash, role, name) VALUES (?, ?, 'team', ?)",
                         (email, generate_password_hash(password), team)).lastrowid
        tid = db.execute("INSERT INTO teams(name, user_id, phone) VALUES (?, ?, ?)",
                         (team, uid, f.get("phone", "").strip()[:30])).lastrowid
        db.executemany("INSERT INTO players(team_id, first_name, last_name, birth_date) VALUES (?, ?, ?, ?)",
                       [(tid, fn[:40], ln[:40], bd) for fn, ln, bd in players])
        db.commit()
        session.clear()
        session["uid"] = uid
        session["csrf"] = secrets.token_urlsafe(24)
        flash("Squadra iscritta! Carica ora i certificati medici o consegnali al responsabile.", "ok")
        return redirect(url_for("main.team_home"))
    return render_template("register.html", min_p=min_p, max_p=max_p, form={},
                           players=[("", "", None)] * min_p)


# --------------------------------------------------------- area squadra

@bp.route("/squadra")
@roles_required("team")
def team_home():
    db = get_db()
    team = S.teams_with_players(db, "t.id = ?", (my_team(db)["id"],))[0]
    matches = [dict(m) for m in db.execute(
        S.MATCH_SELECT + " WHERE m.team1_id = ? OR m.team2_id = ? ORDER BY m.seq",
        (team["id"], team["id"]))]
    standings = next((gr for gr in S.group_data(db) if gr["id"] == team["group_id"]), None)
    return render_template("team_home.html", team=team, matches=matches, group=standings,
                           min_p=S.get_int(db, "min_players", 4), max_p=S.get_int(db, "max_players", 8))


@bp.route("/squadra/giocatori", methods=["POST"])
@roles_required("team")
def player_add():
    db = get_db()
    team = my_team(db)
    fn, ln = request.form.get("first_name", "").strip(), request.form.get("last_name", "").strip()
    n = db.execute("SELECT COUNT(*) FROM players WHERE team_id = ?", (team["id"],)).fetchone()[0]
    if not fn or not ln:
        return fail("Nome e cognome sono obbligatori.", "main.team_home")
    if n >= S.get_int(db, "max_players", 8):
        return fail("Hai raggiunto il numero massimo di giocatori.", "main.team_home")
    db.execute("INSERT INTO players(team_id, first_name, last_name, birth_date) VALUES (?, ?, ?, ?)",
               (team["id"], fn[:40], ln[:40], parse_date(request.form.get("birth_date"))))
    db.commit()
    flash("Giocatore aggiunto.", "ok")
    return redirect(url_for("main.team_home"))


@bp.route("/squadra/giocatori/<int:pid>/modifica", methods=["POST"])
@roles_required("team")
def player_edit(pid):
    db = get_db()
    p = owned_player(db, pid)
    fn, ln = request.form.get("first_name", "").strip(), request.form.get("last_name", "").strip()
    if not fn or not ln:
        return fail("Nome e cognome sono obbligatori.", "main.team_home")
    db.execute("UPDATE players SET first_name = ?, last_name = ?, birth_date = ? WHERE id = ?",
               (fn[:40], ln[:40], parse_date(request.form.get("birth_date")), p["id"]))
    db.commit()
    flash("Giocatore aggiornato.", "ok")
    return redirect(url_for("main.team_home"))


@bp.route("/squadra/giocatori/<int:pid>/elimina", methods=["POST"])
@roles_required("team")
def player_delete(pid):
    db = get_db()
    p = owned_player(db, pid)
    n = db.execute("SELECT COUNT(*) FROM players WHERE team_id = ?", (p["team_id"],)).fetchone()[0]
    if n <= S.get_int(db, "min_players", 4):
        return fail("La squadra deve avere almeno %d giocatori." % S.get_int(db, "min_players", 4),
                    "main.team_home")
    _remove_file(p)
    db.execute("DELETE FROM players WHERE id = ?", (p["id"],))
    db.commit()
    flash("Giocatore rimosso.", "ok")
    return redirect(url_for("main.team_home"))


def _remove_file(p):
    if p.get("cert_file"):
        try:
            os.remove(os.path.join(current_upload_dir(), p["cert_file"]))
        except OSError:
            pass


def current_upload_dir():
    from flask import current_app
    return current_app.config["UPLOAD_DIR"]


@bp.route("/squadra/giocatori/<int:pid>/certificato", methods=["POST"])
@roles_required("team", "boss")
def cert_upload(pid):
    db = get_db()
    p = owned_player(db, pid)
    if g.user["role"] == "team" and p["cert_ok"]:
        return fail("Il certificato è già stato verificato.", "main.team_home")
    back = ("main.admin_team", {"tid": p["team_id"]}) if g.user["role"] == "boss" else ("main.team_home", {})
    f = request.files.get("file")
    if not f or not f.filename:
        return fail("Seleziona un file.", back[0], **back[1])
    head = f.read(8)
    f.seek(0)
    ext = next((e for magic, e in MAGIC.items() if head.startswith(magic)), None)
    if not ext:
        return fail("Formato non valido: usa PDF, JPG o PNG.", back[0], **back[1])
    _remove_file(p)
    name = "%d_%s.%s" % (pid, secrets.token_hex(8), ext)
    f.save(os.path.join(current_upload_dir(), name))
    ok = 1 if g.user["role"] == "boss" else 0
    db.execute("UPDATE players SET cert_file = ?, cert_original_name = ?, cert_uploaded_at = ?, "
               "cert_ok = ? WHERE id = ?",
               (name, os.path.basename(f.filename)[:100], datetime.now().strftime(S.TIME_FMT), ok, pid))
    db.commit()
    flash("Certificato caricato." + ("" if ok else " Il responsabile lo verificherà."), "ok")
    return redirect(url_for(back[0], **back[1]))


@bp.route("/file/<int:pid>")
@roles_required("team", "boss")
def cert_file(pid):
    p = owned_player(get_db(), pid)
    if not p["cert_file"]:
        abort(404)
    return send_from_directory(current_upload_dir(), p["cert_file"],
                               download_name=p["cert_original_name"] or p["cert_file"])


# -------------------------------------------------------------- area tavolo

@bp.route("/tavolo")
@roles_required("scorer", "boss")
def table_home():
    db = get_db()
    live = [dict(m) for m in db.execute(S.MATCH_SELECT + " WHERE m.status = 'live' ORDER BY m.seq")]
    todo = [dict(m) for m in db.execute(
        S.MATCH_SELECT + " WHERE m.status = 'scheduled' AND m.team1_id IS NOT NULL "
        "AND m.team2_id IS NOT NULL ORDER BY m.seq")]
    done = [dict(m) for m in db.execute(
        S.MATCH_SELECT + " WHERE m.status = 'finished' ORDER BY m.finished_at DESC, m.id DESC LIMIT 10")]
    return render_template("table_home.html", live=live, todo=todo, done=done)


@bp.route("/tavolo/<int:match_id>")
@roles_required("scorer", "boss")
def table_match(match_id):
    m = S.get_match(get_db(), match_id)
    if not m:
        abort(404)
    return render_template("table_match.html", m=m)


def match_json(db, match_id):
    m = S.get_match(db, match_id)
    return jsonify(id=m["id"], score1=m["score1"], score2=m["score2"], status=m["status"])


@bp.route("/api/match/<int:match_id>")
def api_match(match_id):
    db = get_db()
    if not S.get_match(db, match_id):
        abort(404)
    return match_json(db, match_id)


@bp.route("/api/match/<int:match_id>/<action>", methods=["POST"])
@roles_required("scorer", "boss")
def api_match_action(match_id, action):
    db = get_db()
    data = request.get_json(silent=True) or {}
    try:
        if action == "point":
            team, delta = int(data.get("team", 0)), int(data.get("delta", 0))
            if team not in (1, 2) or delta not in (-3, -2, -1, 1, 2, 3):
                return jsonify(error="Richiesta non valida"), 400
            S.add_points(db, match_id, team, delta)
        elif action == "set":
            S.set_score(db, match_id, int(data.get("score1", 0)), int(data.get("score2", 0)))
        elif action == "start":
            S.start_match(db, match_id)
        elif action == "finish":
            S.finish_match(db, match_id)
        elif action == "reopen":
            if g.user["role"] != "boss":
                return jsonify(error="Solo il boss può riaprire una partita"), 403
            S.reopen_match(db, match_id)
        else:
            abort(404)
        db.commit()
    except S.TournamentError as e:
        db.rollback()
        return jsonify(error=str(e)), 409
    except (TypeError, ValueError):
        return jsonify(error="Richiesta non valida"), 400
    return match_json(db, match_id)


# --------------------------------------------------------------- area boss

@bp.route("/admin")
@roles_required("boss")
def admin_home():
    db = get_db()
    teams = S.teams_with_players(db)
    missing = [t for t in teams if t["certs_missing"]]
    return render_template("admin/home.html", teams=teams, missing=missing,
                           phase=S.tournament_phase(db), phase_labels=S.PHASE_LABELS,
                           min_p=S.get_int(db, "min_players", 4))


@bp.route("/admin/squadre")
@roles_required("boss")
def admin_teams():
    return render_template("admin/teams.html", teams=S.teams_with_players(get_db()),
                           min_p=S.get_int(get_db(), "min_players", 4))


@bp.route("/admin/squadre/<int:tid>")
@roles_required("boss")
def admin_team(tid):
    teams = S.teams_with_players(get_db(), "t.id = ?", (tid,))
    if not teams:
        abort(404)
    return render_template("admin/team.html", team=teams[0])


@bp.route("/admin/squadre/<int:tid>/stato", methods=["POST"])
@roles_required("boss")
def admin_team_status(tid):
    db = get_db()
    action = request.form.get("action")
    if S.tournament_phase(db) != "registration" and action != "confirm":
        return fail("Dopo il sorteggio non si possono più cambiare le squadre.", "main.admin_team", tid=tid)
    if action == "confirm":
        if S.tournament_phase(db) != "registration":
            return fail("Il sorteggio è già stato fatto: la squadra non entrerebbe nei gironi.",
                        "main.admin_team", tid=tid)
        db.execute("UPDATE teams SET status = 'confirmed' WHERE id = ?", (tid,))
    elif action == "unconfirm":
        db.execute("UPDATE teams SET status = 'pending' WHERE id = ?", (tid,))
    elif action == "delete":
        for p in db.execute("SELECT cert_file FROM players WHERE team_id = ?", (tid,)):
            _remove_file(dict(p))
        uid = db.execute("SELECT user_id FROM teams WHERE id = ?", (tid,)).fetchone()
        db.execute("DELETE FROM teams WHERE id = ?", (tid,))
        if uid and uid["user_id"]:
            db.execute("DELETE FROM users WHERE id = ?", (uid["user_id"],))
        db.commit()
        flash("Squadra eliminata.", "ok")
        return redirect(url_for("main.admin_teams"))
    db.commit()
    return redirect(url_for("main.admin_team", tid=tid))


@bp.route("/admin/giocatori/<int:pid>/cert", methods=["POST"])
@roles_required("boss")
def admin_cert_toggle(pid):
    db = get_db()
    p = owned_player(db, pid)
    db.execute("UPDATE players SET cert_ok = ? WHERE id = ?", (0 if p["cert_ok"] else 1, pid))
    db.commit()
    nxt = request.form.get("next")
    return redirect(url_for("main.admin_home") if nxt == "home"
                    else url_for("main.admin_team", tid=p["team_id"]))


@bp.route("/admin/export/certificati.csv")
@roles_required("boss")
def admin_export():
    lines = ["squadra;cognome;nome;certificato"]
    for t in S.teams_with_players(get_db()):
        for p in t["players"]:
            lines.append(";".join(x.replace(";", ",") for x in (
                t["name"], p["last_name"], p["first_name"],
                {"ok": "OK", "uploaded": "DA VERIFICARE", "missing": "MANCANTE"}[p["cert"]])))
    return Response("﻿" + "\n".join(lines), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=certificati.csv"})


@bp.route("/admin/impostazioni", methods=["GET", "POST"])
@roles_required("boss")
def admin_settings():
    db = get_db()
    if request.method == "POST":
        f = request.form
        S.set_setting(db, "tournament_name", f.get("tournament_name", "").strip()[:80] or "Torneo 3v3")
        S.set_setting(db, "tournament_info", f.get("tournament_info", "").strip()[:2000])
        S.set_setting(db, "registration_open", "1" if f.get("registration_open") else "0")
        for key, lo, hi in (("min_players", 3, 12), ("max_players", 3, 12),
                            ("courts", 1, 8), ("match_minutes", 5, 90)):
            try:
                S.set_setting(db, key, min(hi, max(lo, int(f.get(key, "")))))
            except ValueError:
                pass
        S.set_setting(db, "start_time", f.get("start_time", "").strip())
        db.commit()
        flash("Impostazioni salvate.", "ok")
        return redirect(url_for("main.admin_settings"))
    return render_template("admin/settings.html", s={r["key"]: r["value"] for r in
                                                      db.execute("SELECT * FROM settings")})


@bp.route("/admin/gironi", methods=["GET", "POST"])
@roles_required("boss")
def admin_groups():
    db = get_db()
    if request.method == "POST":
        action = request.form.get("action")
        try:
            if action == "draw":
                S.draw_groups(db, int(request.form.get("n_groups") or 0) or None)
            elif action == "move":
                S.move_team(db, int(request.form["team_id"]), int(request.form["group_id"]))
            elif action == "matches":
                S.generate_group_matches(db)
            elif action == "delete_matches":
                S.delete_group_matches(db)
            elif action == "knockout":
                start = request.form.get("ko_start", "").strip().replace("T", " ")
                S.generate_knockout(db, int(request.form.get("main_size") or 0) or None,
                                    datetime.strptime(start, S.TIME_FMT) if start else None)
            elif action == "delete_knockout":
                S.delete_knockout(db)
            db.commit()
        except S.TournamentError as e:
            db.rollback()
            flash(str(e), "error")
        except ValueError:
            db.rollback()
            flash("Valore non valido.", "error")
        return redirect(url_for("main.admin_groups"))
    n = db.execute("SELECT COUNT(*) FROM teams WHERE status = 'confirmed'").fetchone()[0]
    sizes = []
    if n >= 2:
        try:
            sizes = group_sizes(n)
        except ValueError:
            pass
    groups = []
    for gr in db.execute("SELECT * FROM groups ORDER BY id"):
        groups.append(dict(gr, teams=[dict(t) for t in db.execute(
            "SELECT id, name FROM teams WHERE group_id = ? ORDER BY name", (gr["id"],))]))
    phase = S.tournament_phase(db)
    return render_template("admin/groups.html", n_confirmed=n, suggested=suggest_groups(n),
                           sizes=sizes, groups=groups, phase=phase,
                           complete=S.group_stage_complete(db),
                           main_default=(n + 1) // 2)


@bp.route("/admin/partite", methods=["GET", "POST"])
@roles_required("boss")
def admin_matches():
    db = get_db()
    if request.method == "POST":
        mid = int(request.form["match_id"])
        raw = request.form.get("start_time", "").strip().replace("T", " ")
        try:
            when = datetime.strptime(raw, S.TIME_FMT).strftime(S.TIME_FMT) if raw else None
            court = int(request.form["court"]) if request.form.get("court") else None
        except ValueError:
            return fail("Orario o campo non valido.", "main.admin_matches")
        db.execute("UPDATE matches SET court = ?, start_time = ? WHERE id = ?", (court, when, mid))
        db.commit()
        flash("Partita aggiornata.", "ok")
        return redirect(url_for("main.admin_matches") + "#m%d" % mid)
    matches = [dict(m) for m in db.execute(S.MATCH_SELECT + " ORDER BY m.seq")]
    return render_template("admin/matches.html", matches=matches)


@bp.route("/admin/utenti", methods=["GET", "POST"])
@roles_required("boss")
def admin_users():
    db = get_db()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "create":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            if not EMAIL_RE.match(email) or len(password) < 8:
                return fail("Email valida e password di almeno 8 caratteri richieste.", "main.admin_users")
            if db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
                return fail("Email già in uso.", "main.admin_users")
            db.execute("INSERT INTO users(email, password_hash, role, name) VALUES (?, ?, 'scorer', ?)",
                       (email, generate_password_hash(password), request.form.get("name", "").strip()[:60]))
            flash("Contapunti creato.", "ok")
        elif action == "delete":
            db.execute("DELETE FROM users WHERE id = ? AND role = 'scorer'", (int(request.form["user_id"]),))
        elif action == "password":
            pw = request.form.get("password", "")
            if len(pw) < 8:
                return fail("Password di almeno 8 caratteri.", "main.admin_users")
            db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                       (generate_password_hash(pw), int(request.form["user_id"])))
            flash("Password aggiornata.", "ok")
        db.commit()
        return redirect(url_for("main.admin_users"))
    users = [dict(u) for u in db.execute(
        "SELECT * FROM users WHERE role IN ('scorer', 'boss') ORDER BY role, email")]
    return render_template("admin/users.html", users=users)
