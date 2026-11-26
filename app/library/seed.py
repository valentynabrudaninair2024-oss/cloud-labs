"""Demo data for a fresh database. Safe to run more than once: does nothing if genres already exist.

    docker compose exec app python -m library.seed
"""
from datetime import date, timedelta

from library import db
from library.models import Author, Book, Genre, Holding, Librarian, Library, Loan, Reader

GENRES = ["Роман", "Фантастика", "Поезія", "Історія", "Наукова література"]

AUTHORS = [
    ("Іван Франко", "Україна", 1856),
    ("Леся Українка", "Україна", 1871),
    ("Ліна Костенко", "Україна", 1930),
    ("Станіслав Лем", "Польща", 1921),
    ("Юваль Ной Харарі", "Ізраїль", 1976),
]

# title, isbn, year, pages, author index, genre index
BOOKS = [
    ("Захар Беркут", "978-966-03-0001-1", 1883, 224, 0, 0),
    ("Перехресні стежки", "978-966-03-0002-8", 1900, 352, 0, 0),
    ("Лісова пісня", "978-966-03-0003-5", 1911, 160, 1, 2),
    ("Маруся Чурай", "978-966-03-0004-2", 1979, 208, 2, 2),
    ("Соляріс", "978-966-03-0005-9", 1961, 288, 3, 1),
    ("Кіберіада", "978-966-03-0006-6", 1965, 320, 3, 1),
    ("Sapiens. Людина розумна", "978-966-03-0007-3", 2011, 512, 4, 4),
    ("Homo Deus", "978-966-03-0008-0", 2015, 464, 4, 4),
]

LIBRARIES = [
    ("Центральна міська бібліотека", "вул. Бандери, 12", "Львів", "+380322000001"),
    ("Бібліотека для юнацтва", "пл. Ринок, 5", "Львів", "+380322000002"),
    ("Наукова бібліотека Політехніки", "вул. Професорська, 1", "Львів", "+380322000003"),
]

LIBRARIANS = [
    ("Олена Ковальчук", "director", 0),
    ("Андрій Мельник", "librarian", 0),
    ("Ірина Бойко", "librarian", 1),
    ("Тарас Савчук", "bibliographer", 2),
]

READERS = [
    ("Марія Шевчук", "maria.shevchuk@example.com", "+380671110001"),
    ("Олег Ткаченко", "oleh.tkachenko@example.com", "+380671110002"),
    ("Наталія Гнатюк", "natalia.hnatiuk@example.com", None),
]


def seed():
    if Genre.query.first() is not None:
        return False

    genres = [Genre(name=n) for n in GENRES]
    authors = [Author(full_name=n, country=c, birth_year=y) for n, c, y in AUTHORS]
    books = [Book(title=t, isbn=i, year=y, pages=p, author=authors[a], genre=genres[g])
             for t, i, y, p, a, g in BOOKS]
    libraries = [Library(name=n, address=a, city=c, phone=p) for n, a, c, p in LIBRARIES]
    librarians = [Librarian(full_name=n, position=p, library=libraries[i]) for n, p, i in LIBRARIANS]
    readers = [Reader(full_name=n, email=e, phone=p) for n, e, p in READERS]

    holdings = []
    for li, lib in enumerate(libraries):
        for bi, book in enumerate(books):
            if (li + bi) % 3 != 2:  # not every branch has every book
                copies = 2 + (li + bi) % 3
                holdings.append(Holding(library=lib, book=book, copies_total=copies, copies_available=copies))

    db.session.add_all(genres + authors + books + libraries + librarians + readers + holdings)
    db.session.flush()

    today = date.today()
    first = holdings[0]
    first.copies_available -= 1
    db.session.add(Loan(reader=readers[0], library=first.library, book=first.book,
                        issued_at=today - timedelta(days=20), due_date=today - timedelta(days=6)))
    second = holdings[1]
    second.copies_available -= 1
    db.session.add(Loan(reader=readers[1], library=second.library, book=second.book,
                        issued_at=today - timedelta(days=3), due_date=today + timedelta(days=11)))
    db.session.commit()
    return True


if __name__ == "__main__":
    from app import app

    with app.app_context():
        print("seeded" if seed() else "database already has data, nothing to do")
