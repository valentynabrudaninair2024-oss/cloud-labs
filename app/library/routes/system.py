"""Service endpoints: health check for the ALB, counters for load-test reports."""
from flask import Blueprint, jsonify
from sqlalchemy import text

from library import cache, db

bp = Blueprint("system", __name__)


@bp.get("/")
def index():
    return jsonify({"service": "library api", "status": "running",
                    "resources": ["/libraries", "/books", "/authors", "/genres",
                                  "/readers", "/librarians", "/loans", "/holdings"]})


@bp.get("/health")
def health():
    """Liveness only: does not touch MySQL, so a slow DB does not take tasks out of the ALB."""
    return jsonify({"status": "ok"})


@bp.get("/stats")
def stats():
    """MySQL server counters and cache hits; the load test reads them before and after a run."""
    rows = db.session.execute(text(
        "SHOW GLOBAL STATUS WHERE Variable_name IN ('Questions', 'Com_select', 'Com_insert')"
    )).all()
    return jsonify({"db": {name: int(value) for name, value in rows}, "cache": cache.stats()})
