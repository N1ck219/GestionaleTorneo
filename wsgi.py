import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    # debug solo su richiesta esplicita (FLASK_DEBUG=1): il debugger Werkzeug non va esposto in rete
    app.run(host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", 5000)),
            debug=os.environ.get("FLASK_DEBUG") == "1")
