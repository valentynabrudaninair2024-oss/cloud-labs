"""Book catalogue: genres, authors, books and holdings (copies of a book in a branch)."""
from flask import Blueprint, jsonify, request
from sqlalchemy import func

from library import db
from library.http import ApiError, commit, get_or_404, json_body, limit_arg, pick
from library.models import Author, Book, Genre, Holding, Library

bp = Blueprint("catalog", __name__)

AUTHOR_FIELDS = ("full_name", "country", "birth_year")
BOOK_FIELDS = ("title", "isbn", "year", "pages", "author_id", "genre_id")


# --- genres ---------------------------------------------------------------

@bp.get("/genres")
def list_genres():
    """Genres with the number of books in each."""
    rows = (db.session.query(Genre, func.count(Book.id))
            .outerjoin(Book, Book.genre_id == Genre.id)
            .group_by(Genre.id)
            .order_by(Genre.name)
            .all())
    return jsonify([{**g.to_dict(), "books": n} for g, n in rows])


@bp.post("/genres")
def create_genre():
    genre = Genre(name=json_body(["name"])["name"])
    db.session.add(genre)
    commit()
    return jsonify(genre.to_dict()), 201


# --- authors --------------------------------------------------------------

@bp.get("/authors")
def list_authors():
    return jsonify([a.to_dict() for a in Author.query.order_by(Author.full_name).all()])


@bp.get("/authors/<int:author_id>")
def get_author(author_id):
    author = get_or_404(Author, author_id)
    return jsonify({**author.to_dict(), "books": [b.to_dict() for b in author.books]})


@bp.post("/authors")
def create_author():
    author = Author(**pick(json_body(["full_name"]), AUTHOR_FIELDS))
    db.session.add(author)
    commit()
    return jsonify(author.to_dict()), 201


@bp.put("/authors/<int:author_id>")
def update_author(author_id):
    author = get_or_404(Author, author_id)
    for field, value in pick(json_body(), AUTHOR_FIELDS).items():
        setattr(author, field, value)
    commit()
    return jsonify(author.to_dict())


@bp.delete("/authors/<int:author_id>")
def delete_author(author_id):
    author = get_or_404(Author, author_id)
    if author.books:
        raise ApiError(409, "Author still has books in the catalogue")
    db.session.delete(author)
    commit()
    return "", 204


# --- books ----------------------------------------------------------------

@bp.get("/books")
def list_books():
    """Optional filters: ?genre_id=, ?author_id=, ?q= (part of the title), ?limit=."""
    query = Book.query
    if (genre_id := request.args.get("genre_id", type=int)) is not None:
        query = query.filter(Book.genre_id == genre_id)
    if (author_id := request.args.get("author_id", type=int)) is not None:
        query = query.filter(Book.author_id == author_id)
    if q := request.args.get("q"):
        query = query.filter(Book.title.like(f"%{q}%"))
    return jsonify([b.to_dict() for b in query.order_by(Book.title).limit(limit_arg()).all()])


@bp.get("/books/<int:book_id>")
def get_book(book_id):
    book = get_or_404(Book, book_id)
    available = sum(h.copies_available for h in book.holdings)
    return jsonify({**book.to_dict(),
                    "author": book.author.full_name,
                    "genre": book.genre.name if book.genre else None,
                    "copies_available": available,
                    "libraries": [h.to_dict() for h in book.holdings]})


@bp.post("/books")
def create_book():
    data = json_body(["title", "isbn", "author_id"])
    get_or_404(Author, data["author_id"])
    if data.get("genre_id") is not None:
        get_or_404(Genre, data["genre_id"])
    book = Book(**pick(data, BOOK_FIELDS))
    db.session.add(book)
    commit()
    return jsonify(book.to_dict()), 201


@bp.put("/books/<int:book_id>")
def update_book(book_id):
    book = get_or_404(Book, book_id)
    for field, value in pick(json_body(), BOOK_FIELDS).items():
        setattr(book, field, value)
    commit()
    return jsonify(book.to_dict())


@bp.delete("/books/<int:book_id>")
def delete_book(book_id):
    db.session.delete(get_or_404(Book, book_id))
    commit()
    return "", 204


# --- holdings -------------------------------------------------------------

@bp.post("/holdings")
def add_copies():
    """Deliver copies of a book to a branch: creates the holding or adds to it."""
    data = json_body(["library_id", "book_id"])
    copies = data.get("copies", 1)
    if not isinstance(copies, int) or copies < 1:
        raise ApiError(400, "Field 'copies' must be a positive integer")
    get_or_404(Library, data["library_id"])
    get_or_404(Book, data["book_id"])

    holding = (Holding.query
               .filter_by(library_id=data["library_id"], book_id=data["book_id"])
               .with_for_update()
               .first())
    created = holding is None
    if created:
        holding = Holding(library_id=data["library_id"], book_id=data["book_id"],
                          copies_total=0, copies_available=0)
        db.session.add(holding)
    holding.copies_total += copies
    holding.copies_available += copies
    commit()
    return jsonify(holding.to_dict()), 201 if created else 200
