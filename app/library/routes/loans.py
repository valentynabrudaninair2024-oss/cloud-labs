"""Issuing and returning books. The holding row is locked, so two readers cannot take the last copy."""
from datetime import date, timedelta

from flask import Blueprint, jsonify, request

from library import db
from library.http import ApiError, commit, get_or_404, json_body, limit_arg
from library.models import Holding, Loan, Reader

bp = Blueprint("loans", __name__)

DEFAULT_DAYS = 14
MAX_DAYS = 60
MAX_ACTIVE_LOANS = 5


@bp.get("/loans")
def list_loans():
    """?active=true — books not returned yet; ?overdue=true — not returned and past the due date."""
    query = Loan.query
    if request.args.get("active") == "true":
        query = query.filter(Loan.returned_at.is_(None))
    if request.args.get("overdue") == "true":
        query = query.filter(Loan.returned_at.is_(None), Loan.due_date < date.today())
    rows = query.order_by(Loan.id.desc()).limit(limit_arg()).all()
    return jsonify([loan.to_dict() for loan in rows])


@bp.get("/loans/<int:loan_id>")
def get_loan(loan_id):
    return jsonify(get_or_404(Loan, loan_id).to_dict())


@bp.post("/loans")
def issue_book():
    data = json_body(["reader_id", "library_id", "book_id"])
    days = data.get("days", DEFAULT_DAYS)
    if not isinstance(days, int) or not 1 <= days <= MAX_DAYS:
        raise ApiError(400, f"Field 'days' must be an integer from 1 to {MAX_DAYS}")

    get_or_404(Reader, data["reader_id"])
    active = Loan.query.filter_by(reader_id=data["reader_id"], returned_at=None).count()
    if active >= MAX_ACTIVE_LOANS:
        raise ApiError(409, f"Reader already has {MAX_ACTIVE_LOANS} books on hand")

    holding = (Holding.query
               .filter_by(library_id=data["library_id"], book_id=data["book_id"])
               .with_for_update()
               .first())
    if holding is None:
        raise ApiError(404, "This library does not have this book")
    if holding.copies_available < 1:
        db.session.rollback()
        raise ApiError(409, "No copies available right now")

    holding.copies_available -= 1
    today = date.today()
    loan = Loan(reader_id=data["reader_id"], library_id=data["library_id"], book_id=data["book_id"],
                issued_at=today, due_date=today + timedelta(days=days))
    db.session.add(loan)
    commit()
    return jsonify(loan.to_dict()), 201


@bp.post("/loans/<int:loan_id>/return")
def return_book(loan_id):
    loan = db.session.get(Loan, loan_id, with_for_update=True)
    if loan is None:
        raise ApiError(404, f"Loan {loan_id} not found")
    if loan.returned_at is not None:
        db.session.rollback()
        raise ApiError(409, "Book has already been returned")

    holding = (Holding.query
               .filter_by(library_id=loan.library_id, book_id=loan.book_id)
               .with_for_update()
               .first())
    if holding is not None:
        holding.copies_available = min(holding.copies_available + 1, holding.copies_total)
    loan.returned_at = date.today()
    commit()
    return jsonify(loan.to_dict())
