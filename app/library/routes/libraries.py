"""Library branches: the hot read path (cached list) and the write paths (sync, idempotent, async via SQS)."""
import logging
import uuid

from flask import Blueprint, jsonify, url_for

from library import cache, db, jobs, sqs
from library.http import ApiError, commit, get_or_404, json_body, limit_arg, pick
from library.idempotency import idempotent
from library.models import Book, Holding, Librarian, Library

log = logging.getLogger(__name__)

bp = Blueprint("libraries", __name__)

FIELDS = ("name", "address", "city", "phone")
REQUIRED = FIELDS


def list_cache_key(limit):
    return f"libraries:list:{limit}"


@bp.get("/libraries")
def list_libraries():
    limit = limit_arg()
    key = list_cache_key(limit)
    data, status = cache.get_json(key)
    if data is None:
        rows = Library.query.order_by(Library.id.desc()).limit(limit).all()
        data = [lib.to_dict() for lib in rows]
        cache.set_json(key, data)
    resp = jsonify(data)
    resp.headers["X-Cache"] = status
    return resp


@bp.get("/libraries/<int:library_id>")
def get_library(library_id):
    return jsonify(get_or_404(Library, library_id).to_dict())


@bp.get("/libraries/<int:library_id>/librarians")
def library_librarians(library_id):
    rows = Librarian.query.filter_by(library_id=library_id).order_by(Librarian.full_name).all()
    return jsonify([r.to_dict() for r in rows])


@bp.get("/libraries/<int:library_id>/books")
def library_books(library_id):
    """Catalogue of one branch: which books it has and how many copies are on the shelf."""
    get_or_404(Library, library_id)
    rows = (db.session.query(Holding, Book)
            .join(Book, Holding.book_id == Book.id)
            .filter(Holding.library_id == library_id)
            .order_by(Book.title)
            .all())
    return jsonify([{**book.to_dict(), "copies_total": h.copies_total,
                     "copies_available": h.copies_available} for h, book in rows])


@bp.post("/libraries")
@idempotent
def create_library():
    data = json_body(REQUIRED)
    lib = Library(**pick(data, FIELDS))
    db.session.add(lib)
    commit()
    resp = jsonify(lib.to_dict())
    resp.status_code = 201
    resp.headers["Location"] = url_for("libraries.get_library", library_id=lib.id)
    return resp


@bp.post("/libraries/async")
@idempotent
def create_library_async():
    """Accept the write, put it into SQS and answer 202 at once; the worker writes to MySQL."""
    data = json_body(REQUIRED)
    if not sqs.enabled():
        raise ApiError(503, "Queue is not configured")

    job_id = str(uuid.uuid4())
    try:
        jobs.save(job_id, "queued")
        sqs.send({"job_id": job_id, "op": "create_library", "data": pick(data, FIELDS)})
    except Exception as e:
        log.exception("enqueue of job %s failed", job_id)
        try:
            jobs.save(job_id, "failed", error="enqueue failed")
        except Exception:
            pass
        raise ApiError(503, f"Could not enqueue: {e}")

    status_url = url_for("libraries.get_job", job_id=job_id)
    resp = jsonify({"job_id": job_id, "status": "queued", "status_url": status_url})
    resp.status_code = 202
    resp.headers["Location"] = status_url
    return resp


@bp.get("/jobs/<job_id>")
def get_job(job_id):
    job = jobs.get(job_id)
    if not job:
        raise ApiError(404, "Job not found")
    return jsonify(job)


@bp.put("/libraries/<int:library_id>")
def update_library(library_id):
    lib = get_or_404(Library, library_id)
    for field, value in pick(json_body(), FIELDS).items():
        setattr(lib, field, value)
    commit()
    return jsonify(lib.to_dict())


@bp.delete("/libraries/<int:library_id>")
def delete_library(library_id):
    db.session.delete(get_or_404(Library, library_id))
    commit()
    return "", 204
