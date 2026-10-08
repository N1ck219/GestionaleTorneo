import re

import pytest

from app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("BOSS_EMAIL", "boss@x.it")
    monkeypatch.setenv("BOSS_PASSWORD", "bosspass123")
    app = create_app({"DATA_DIR": str(tmp_path), "DB_PATH": str(tmp_path / "t.db"),
                      "UPLOAD_DIR": str(tmp_path / "up"), "TESTING": True,
                      "SECRET_KEY": "test"})
    return app.test_client()


def csrf(c, path="/"):
    html = c.get(path).get_data(as_text=True)
    return re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)


def post(c, path, data=None, **kw):
    data = dict(data or {})
    data["_csrf"] = csrf(c)
    return c.post(path, data=data, **kw)


def login(c, email, pw):
    r = post(c, "/login", {"email": email, "password": pw})
    assert r.status_code == 302, r.get_data(as_text=True)


def register_team(c, name, n=4):
    data = {"team_name": name, "email": name.lower() + "@x.it", "password": "password1",
            "first_name": ["Nome%d" % i for i in range(n)], "last_name": ["Cog%s%d" % (name, i) for i in range(n)],
            "birth_date": [""] * n}
    r = post(c, "/iscrizione", data)
    assert r.status_code == 302, r.get_data(as_text=True)


def api(c, path, body=None):
    return c.post(path, json=body or {}, headers={"X-CSRF-Token": csrf(c)})


def test_csrf_required(client):
    assert client.post("/login", data={"email": "a", "password": "b"}).status_code == 400


def test_registration_rules(client):
    r = post(client, "/iscrizione", {"team_name": "X", "email": "x@x.it", "password": "password1",
                                    "first_name": ["a", "b", "c"], "last_name": ["a", "b", "c"],
                                    "birth_date": ["", "", ""]})
    assert r.status_code == 400 and b"almeno 4" in r.data


def test_full_tournament(client, tmp_path):
    c = client
    names = ["Alfa", "Beta", "Gamma", "Delta", "Eps", "Zeta", "Eta", "Theta", "Iota"]
    for n in names:
        register_team(c, n)
        post(c, "/logout")
    login(c, "boss@x.it", "bosspass123")

    # certificati mancanti visibili subito al boss
    home = c.get("/admin").get_data(as_text=True)
    assert "Certificati medici mancanti" in home and "CogAlfa0" in home

    for tid in range(1, 10):
        post(c, "/admin/squadre/%d/stato" % tid, {"action": "confirm"})
    # un certificato consegnato a mano: sparisce dall'elenco mancanti
    post(c, "/admin/giocatori/1/cert", {"next": "home"})
    assert "CogAlfa0" not in c.get("/admin").get_data(as_text=True)

    # calendario prima del sorteggio: errore gestito
    post(c, "/admin/gironi", {"action": "matches"})
    post(c, "/admin/gironi", {"action": "draw"})
    page = c.get("/admin/gironi").get_data(as_text=True)
    assert "Girone C" in page and "Girone D" not in page      # 9 squadre -> 3 gironi da 3
    post(c, "/admin/gironi", {"action": "matches"})
    assert c.get("/calendario").get_data(as_text=True).count('class="match scheduled"') == 9

    # contapunti
    post(c, "/admin/utenti", {"action": "create", "email": "s@x.it", "password": "scorer123", "name": "S"})
    post(c, "/logout")
    login(c, "s@x.it", "scorer123")
    assert c.get("/admin").status_code == 403

    from app.db import connect
    ids = [r["id"] for r in connect(c.application.config["DB_PATH"]).execute(
        "SELECT id FROM matches ORDER BY seq")]
    for mid in ids:
        assert api(c, "/api/match/%d/finish" % mid).status_code == 409       # non iniziata
        assert api(c, "/api/match/%d/start" % mid).status_code == 200
        api(c, "/api/match/%d/point" % mid, {"team": 1, "delta": 2})
        api(c, "/api/match/%d/point" % mid, {"team": 1, "delta": 1})
        api(c, "/api/match/%d/point" % mid, {"team": 2, "delta": 1})
        assert "LIVE" in c.get("/").get_data(as_text=True)
        r = api(c, "/api/match/%d/finish" % mid)
        assert r.status_code == 200 and r.get_json()["status"] == "finished"
        assert api(c, "/api/match/%d/point" % mid, {"team": 1, "delta": 1}).status_code == 409
    assert "Pt" in c.get("/gironi").get_data(as_text=True)

    # parità non chiudibile
    post(c, "/logout")
    login(c, "boss@x.it", "bosspass123")
    post(c, "/admin/gironi", {"action": "knockout"})
    assert "Finale" in c.get("/tabellone").get_data(as_text=True)
    from app import service as S
    db = connect(c.application.config["DB_PATH"])
    assert S.tournament_phase(db) == "knockout"
    # 9 squadre: principale 5, consolazione 4 -> 4 + 3 = 7 partite
    assert db.execute("SELECT COUNT(*) FROM matches WHERE phase='main'").fetchone()[0] == 4
    assert db.execute("SELECT COUNT(*) FROM matches WHERE phase='cons'").fetchone()[0] == 3

    # gioca tutta la fase finale turno per turno
    for _ in range(4):
        row = db.execute("SELECT id FROM matches WHERE status='scheduled' AND team1_id IS NOT NULL "
                         "AND team2_id IS NOT NULL ORDER BY seq").fetchall()
        for r in row:
            assert api(c, "/api/match/%d/start" % r["id"]).status_code == 200
            api(c, "/api/match/%d/point" % r["id"], {"team": 2, "delta": 2})
            assert api(c, "/api/match/%d/finish" % r["id"]).status_code == 200
    db = connect(c.application.config["DB_PATH"])
    assert db.execute("SELECT COUNT(*) FROM matches WHERE status!='finished'").fetchone()[0] == 0


def test_team_area_and_cert_upload(client, tmp_path):
    c = client
    register_team(c, "Alfa")
    page = c.get("/squadra").get_data(as_text=True)
    assert "Mancano 4 certificati" in page
    pdf = (tmp_path / "c.pdf")
    pdf.write_bytes(b"%PDF-1.4 test")
    r = c.post("/squadra/giocatori/1/certificato", data={
        "_csrf": csrf(c), "file": (open(pdf, "rb"), "cert.pdf")}, content_type="multipart/form-data")
    assert r.status_code == 302
    assert "Da verificare" in c.get("/squadra").get_data(as_text=True)
    assert c.get("/file/1").data == b"%PDF-1.4 test"
    bad = c.post("/squadra/giocatori/2/certificato", data={
        "_csrf": csrf(c), "file": (open(__file__, "rb"), "x.pdf")}, content_type="multipart/form-data")
    assert bad.status_code == 302 and "Formato non valido" in c.get("/squadra").get_data(as_text=True)
    # un'altra squadra non può vedere il file
    post(c, "/logout")
    register_team(c, "Beta")
    assert c.get("/file/1").status_code == 403
