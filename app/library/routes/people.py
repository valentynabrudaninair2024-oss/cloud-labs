"""Librarians (staff of a branch) and readers."""
from flask import Blueprint, jsonify

from library import db
from library.http import commit, get_or_404, json_body, limit_arg, pick
from library.models import Librarian, Library, Reader

bp = Blueprint("people", __name__)

LIBRARIAN_FIELDS = ("full_name", "position", "library_id")
READER_FIELDS = ("full_name", "email", "phone")


@bp.get("/librarians")
def list_librarians():
    return jsonify([x.to_dict() for x in Librarian.query.order_by(Librarian.id).all()])


@bp.post("/librarians")
def create_librarian():
    data = json_body(["full_name", "library_id"])
    get_or_404(Library, data["library_id"])
    librarian = Librarian(**pick(data, LIBRARIAN_FIELDS))
    db.session.add(librarian)
    commit()
    return jsonify(librarian.to_dict()), 201


@bp.put("/librarians/<int:librarian_id>")
def update_librarian(librarian_id):
    librarian = get_or_404(Librarian, librarian_id)
    data = json_body()
    if "library_id" in data:
        get_or_404(Library, data["library_id"])
    for field, value in pick(data, LIBRARIAN_FIELDS).items():
        setattr(librarian, field, value)
    commit()
    return jsonify(librarian.to_dict())


@bp.delete("/librarians/<int:librarian_id>")
def delete_librarian(librarian_id):
    db.session.delete(get_or_404(Librarian, librarian_id))
    commit()
    return "", 204


@bp.get("/readers")
def list_readers():
    rows = Reader.query.order_by(Reader.id.desc()).limit(limit_arg()).all()
    return jsonify([r.to_dict() for r in rows])


@bp.get("/readers/<int:reader_id>")
def get_reader(reader_id):
    reader = get_or_404(Reader, reader_id)
    return jsonify({**reader.to_dict(), "loans": [loan.to_dict() for loan in reader.loans]})


@bp.post("/readers")
def create_reader():
    reader = Reader(**pick(json_body(["full_name", "email"]), READER_FIELDS))
    db.session.add(reader)
    commit()
    return jsonify(reader.to_dict()), 201


@bp.put("/readers/<int:reader_id>")
def update_reader(reader_id):
    reader = get_or_404(Reader, reader_id)
    for field, value in pick(json_body(), READER_FIELDS).items():
        setattr(reader, field, value)
    commit()
    return jsonify(reader.to_dict())


@bp.delete("/readers/<int:reader_id>")
def delete_reader(reader_id):
    db.session.delete(get_or_404(Reader, reader_id))
    commit()
    return "", 204
