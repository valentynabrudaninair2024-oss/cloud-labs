"""Entry point of the Library API (gunicorn app:app)."""
import logging
import os
import time

from flask import Flask
from sqlalchemy.exc import SQLAlchemyError

from library import db
from library.http import register_error_handlers
from library.routes import BLUEPRINTS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("library")


def database_url():
    return (
        f"mysql+mysqlconnector://{os.environ['DB_USER']}:{os.environ['DB_PASSWORD']}"
        f"@{os.environ['DB_HOST']}:{os.environ.get('DB_PORT', '3306')}/{os.environ['DB_NAME']}"
    )


def create_tables(app, attempts=20, delay=3):
    """RDS / the MySQL container may still be starting, so retry instead of crashing the task."""
    with app.app_context():
        for attempt in range(1, attempts + 1):
            try:
                db.create_all()
                return
            except SQLAlchemyError as e:
                log.warning("database not ready (%s/%s): %s", attempt, attempts, e.__class__.__name__)
                time.sleep(delay)
    raise RuntimeError("Database is unavailable")


def create_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url()
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "pool_recycle": 1800}
    app.json.ensure_ascii = False

    db.init_app(app)
    for blueprint in BLUEPRINTS:
        app.register_blueprint(blueprint)
    register_error_handlers(app)

    create_tables(app)
    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
