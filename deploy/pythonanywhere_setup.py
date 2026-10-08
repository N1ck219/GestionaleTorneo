#!/usr/bin/env python3
"""Installa (o aggiorna) il gestionale su PythonAnywhere.

Si lancia dalla console Bash di PythonAnywhere:

    curl -fsSL https://raw.githubusercontent.com/N1ck219/GestionaleTorneo/claude/basketball-tournament-manager-qek7s7/deploy/pythonanywhere_setup.py -o setup.py && python3 setup.py

Fa tutto da solo: scarica il codice, crea l'ambiente Python, crea e configura il sito web,
crea l'account boss e ricarica il sito. Rilanciandolo aggiorna il sito mantenendo i dati.
Richiede solo il token API (Account -> API token) che gli viene chiesto una volta.
"""
import getpass
import json
import os
import secrets
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

REPO = os.environ.get("REPO_URL", "https://github.com/N1ck219/GestionaleTorneo.git")
BRANCH = os.environ.get("BRANCH", "claude/basketball-tournament-manager-qek7s7")
USER = getpass.getuser()
DOMAIN = "%s.pythonanywhere.com" % USER.lower()   # PythonAnywhere usa sempre minuscole
HOME = os.path.expanduser("~")
APP_DIR = os.path.join(HOME, "GestionaleTorneo")
DATA_DIR = os.path.join(HOME, "torneo-data")
CONF = os.path.join(DATA_DIR, "deploy.json")           # ricorda email boss e password iniziale
WSGI_FILE = "/var/www/%s_wsgi.py" % DOMAIN.replace(".", "_")  # valore atteso; vedi find_wsgi()
API = "https://www.pythonanywhere.com/api/v0/user/%s" % USER
PYVER = "python%d%d" % sys.version_info[:2]

WSGI_TEMPLATE = '''import os, sys
sys.path.insert(0, {app_dir!r})
os.environ["DATA_DIR"] = {data_dir!r}
os.environ["BOSS_EMAIL"] = {email!r}
os.environ["BOSS_PASSWORD"] = {password!r}
os.environ["COOKIE_SECURE"] = "1"
from wsgi import app as application
'''


def run(*cmd, cwd=None):
    print("  $", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def api(method, path, token, data=None):
    req = urllib.request.Request(
        API + path, method=method, headers={"Authorization": "Token " + token},
        data=urllib.parse.urlencode(data).encode() if data else None)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def find_wsgi():
    """Il file WSGI creato da PythonAnywhere: quello atteso, altrimenti l'unico presente in /var/www."""
    import glob
    if os.path.exists(WSGI_FILE):
        return WSGI_FILE
    found = glob.glob("/var/www/*_wsgi.py")
    if len(found) == 1:
        return found[0]
    sys.exit("Non trovo il file WSGI del sito in /var/www (trovati: %s)." % (found or "nessuno"))


def main():
    print("== Gestionale Torneo su PythonAnywhere (%s) ==" % DOMAIN)
    token = os.environ.get("API_TOKEN") or getpass.getpass(
        "Incolla il token API (PythonAnywhere -> Account -> API token), poi Invio: ").strip()
    os.makedirs(DATA_DIR, exist_ok=True)

    # 1. codice
    print("\n[1/5] Scarico il codice")
    if os.path.isdir(os.path.join(APP_DIR, ".git")):
        run("git", "fetch", "origin", BRANCH, cwd=APP_DIR)
        run("git", "checkout", "-B", BRANCH, "origin/" + BRANCH, cwd=APP_DIR)
    else:
        run("git", "clone", "--branch", BRANCH, REPO, APP_DIR)

    # 2. ambiente Python
    print("\n[2/5] Preparo l'ambiente Python (%s)" % PYVER)
    venv = os.path.join(APP_DIR, ".venv")
    if not os.path.isdir(venv):
        run(sys.executable, "-m", "venv", venv)
    run(os.path.join(venv, "bin", "pip"), "install", "-q", "-r", os.path.join(APP_DIR, "requirements.txt"))

    # 3. account boss (la prima volta; poi si riusa)
    print("\n[3/5] Account organizzatore (boss)")
    conf = json.load(open(CONF)) if os.path.exists(CONF) else {}
    if not conf:
        email = os.environ.get("BOSS_EMAIL") or input("Email del boss (servirà per accedere): ").strip()
        conf = {"email": email, "password": os.environ.get("BOSS_PASSWORD") or secrets.token_urlsafe(12)}
        json.dump(conf, open(CONF, "w"))
        os.chmod(CONF, 0o600)

    # 4. sito web
    print("\n[4/5] Configuro il sito web")
    status, body = api("POST", "/webapps/", token, {"domain_name": DOMAIN, "python_version": PYVER})
    if status in (200, 201):
        print("  sito creato")
    elif status == 400 and "already" in body.lower():
        print("  sito già esistente")
    elif status in (401, 403):
        sys.exit("Token API non valido o non autorizzato (%s). Controlla di averlo copiato intero." % status)
    else:
        sys.exit("Creazione del sito non riuscita (%s): %s" % (status, body[:300]))
    status, body = api("PATCH", "/webapps/%s/" % DOMAIN, token,
                       {"virtualenv_path": venv, "source_directory": APP_DIR, "force_https": "true"})
    if status != 200:
        sys.exit("Configurazione del sito non riuscita (%s): %s" % (status, body[:300]))
    wsgi = find_wsgi()
    with open(wsgi, "w") as f:
        f.write(WSGI_TEMPLATE.format(app_dir=APP_DIR, data_dir=DATA_DIR, email=conf["email"], password=conf["password"]))
    print("  file di configurazione scritto:", wsgi)

    # 5. riavvio
    print("\n[5/5] Ricarico il sito")
    status, body = api("POST", "/webapps/%s/reload/" % DOMAIN, token)
    if status != 200:
        sys.exit("Ricarica non riuscita (%s): %s" % (status, body[:300]))

    print("\n" + "=" * 60)
    print("FATTO!  Sito:  https://%s" % DOMAIN)
    print("Accesso boss:  %s  /  %s" % (conf["email"], conf["password"]))
    print("(password anche in %s)" % CONF)
    print("Per aggiornare in futuro basta rilanciare:  python3 setup.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
