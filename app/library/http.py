"""Small helpers shared by all routes: input validation, 404 lookups and safe commits."""
from datetime import date

from flask import jsonify, request
from sqlalchemy.exc import IntegrityError

from library import db


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def _api_error(e):
        return jsonify({"error": e.message}), e.status

    @app.errorhandler(404)
    def _not_found(_):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(405)
    def _method_not_allowed(_):
        return jsonify({"error": "Method not allowed"}), 405


def json_body(required=()):
    """Return the JSON object of the request; 400 if it is missing or lacks required fields."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not data:
        raise ApiError(400, "Request body must be a non-empty JSON object")
    missing = [f for f in required if data.get(f) in (None, "")]
    if missing:
        raise ApiError(400, f"Missing required fields: {', '.join(missing)}")
    return data


def pick(data, fields):
    """Only the fields the model allows to be set from the outside."""
    return {f: data[f] for f in fields if f in data}


def parse_date(value, field):
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ApiError(400, f"Field '{field}' must be a date in YYYY-MM-DD format")


def get_or_404(model, obj_id):
    obj = db.session.get(model, obj_id)
    if obj is None:
        raise ApiError(404, f"{model.__name__} {obj_id} not found")
    return obj


def commit():
    """Commit, turning unique / foreign key violations into 409 Conflict."""
    try:
        db.session.commit()
    except IntegrityError as e:
        db.session.rollback()
        raise ApiError(409, f"Conflict with existing data: {e.orig}")


def limit_arg(default=50, maximum=200):
    value = request.args.get("limit", default, type=int)
    return max(1, min(value, maximum))
