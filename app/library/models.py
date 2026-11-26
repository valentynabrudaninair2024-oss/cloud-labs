"""Database schema of the library.

libraries ─┬─< librarians
           ├─< holdings >── books >── authors
           │                  └────> genres
           └─< loans >── readers
processed_jobs — job ids already handled by the queue worker.
"""
from datetime import date

from library import db


def _iso(value):
    return value.isoformat() if value else None


class Library(db.Model):
    """A library branch. The most read resource: GET /libraries is cached."""

    __tablename__ = "libraries"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(150), nullable=False)
    city = db.Column(db.String(60), nullable=False, index=True)
    phone = db.Column(db.String(20), nullable=False, unique=True)

    librarians = db.relationship("Librarian", back_populates="library", cascade="all, delete-orphan")
    holdings = db.relationship("Holding", back_populates="library", cascade="all, delete-orphan")
    loans = db.relationship("Loan", back_populates="library", cascade="all, delete-orphan")

    def to_dict(self):
        return {"id": self.id, "name": self.name, "address": self.address,
                "city": self.city, "phone": self.phone}


class Librarian(db.Model):
    __tablename__ = "librarians"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    position = db.Column(db.String(50), nullable=False, default="librarian")
    library_id = db.Column(db.Integer, db.ForeignKey("libraries.id", ondelete="CASCADE"), nullable=False, index=True)

    library = db.relationship("Library", back_populates="librarians")

    def to_dict(self):
        return {"id": self.id, "full_name": self.full_name,
                "position": self.position, "library_id": self.library_id}


class Genre(db.Model):
    __tablename__ = "genres"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)

    books = db.relationship("Book", back_populates="genre")

    def to_dict(self):
        return {"id": self.id, "name": self.name}


class Author(db.Model):
    __tablename__ = "authors"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    country = db.Column(db.String(60))
    birth_year = db.Column(db.SmallInteger)

    books = db.relationship("Book", back_populates="author")

    def to_dict(self):
        return {"id": self.id, "full_name": self.full_name,
                "country": self.country, "birth_year": self.birth_year}


class Book(db.Model):
    __tablename__ = "books"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    isbn = db.Column(db.String(17), nullable=False, unique=True)
    year = db.Column(db.SmallInteger)
    pages = db.Column(db.SmallInteger)
    author_id = db.Column(db.Integer, db.ForeignKey("authors.id", ondelete="RESTRICT"), nullable=False, index=True)
    genre_id = db.Column(db.Integer, db.ForeignKey("genres.id", ondelete="SET NULL"), index=True)

    author = db.relationship("Author", back_populates="books")
    genre = db.relationship("Genre", back_populates="books")
    holdings = db.relationship("Holding", back_populates="book", cascade="all, delete-orphan")

    def to_dict(self):
        return {"id": self.id, "title": self.title, "isbn": self.isbn, "year": self.year,
                "pages": self.pages, "author_id": self.author_id, "genre_id": self.genre_id}


class Holding(db.Model):
    """How many copies of a book a branch owns and how many are on the shelf now."""

    __tablename__ = "holdings"
    __table_args__ = (
        db.UniqueConstraint("library_id", "book_id", name="uq_holding_library_book"),
        db.CheckConstraint("copies_available >= 0 AND copies_available <= copies_total",
                           name="ck_holding_copies"),
    )

    id = db.Column(db.Integer, primary_key=True)
    library_id = db.Column(db.Integer, db.ForeignKey("libraries.id", ondelete="CASCADE"), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True)
    copies_total = db.Column(db.Integer, nullable=False, default=1)
    copies_available = db.Column(db.Integer, nullable=False, default=1)

    library = db.relationship("Library", back_populates="holdings")
    book = db.relationship("Book", back_populates="holdings")

    def to_dict(self):
        return {"id": self.id, "library_id": self.library_id, "book_id": self.book_id,
                "copies_total": self.copies_total, "copies_available": self.copies_available}


class Reader(db.Model):
    __tablename__ = "readers"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False, unique=True)
    phone = db.Column(db.String(20))
    registered_at = db.Column(db.Date, nullable=False, default=date.today)

    loans = db.relationship("Loan", back_populates="reader", cascade="all, delete-orphan")

    def to_dict(self):
        return {"id": self.id, "full_name": self.full_name, "email": self.email,
                "phone": self.phone, "registered_at": _iso(self.registered_at)}


class Loan(db.Model):
    """A book issued to a reader in a given branch. returned_at is NULL while the book is out."""

    __tablename__ = "loans"

    id = db.Column(db.Integer, primary_key=True)
    reader_id = db.Column(db.Integer, db.ForeignKey("readers.id", ondelete="CASCADE"), nullable=False, index=True)
    library_id = db.Column(db.Integer, db.ForeignKey("libraries.id", ondelete="CASCADE"), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    issued_at = db.Column(db.Date, nullable=False, default=date.today)
    due_date = db.Column(db.Date, nullable=False)
    returned_at = db.Column(db.Date)

    reader = db.relationship("Reader", back_populates="loans")
    library = db.relationship("Library", back_populates="loans")
    book = db.relationship("Book")

    def to_dict(self):
        return {"id": self.id, "reader_id": self.reader_id, "library_id": self.library_id,
                "book_id": self.book_id, "issued_at": _iso(self.issued_at),
                "due_date": _iso(self.due_date), "returned_at": _iso(self.returned_at),
                "overdue": self.returned_at is None and self.due_date < date.today()}


class ProcessedJob(db.Model):
    """Written in the same transaction as the library it created, so a redelivered message is a no-op."""

    __tablename__ = "processed_jobs"

    job_id = db.Column(db.String(36), primary_key=True)
    library_id = db.Column(db.Integer, nullable=False)
    processed_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
