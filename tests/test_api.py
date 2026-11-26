"""Functional tests of the Library API. Run against `docker compose up`: python -m pytest -v tests/"""
import requests

from conftest import new_library, url


def test_health():
    assert requests.get(url("/health"), timeout=5).json() == {"status": "ok"}


def test_library_crud(library):
    lib_id = library["id"]
    assert requests.get(url(f"/libraries/{lib_id}"), timeout=5).json()["phone"] == library["phone"]

    r = requests.put(url(f"/libraries/{lib_id}"), json={"address": "вул. Нова, 2"}, timeout=5)
    assert r.status_code == 200 and r.json()["address"] == "вул. Нова, 2"

    assert requests.delete(url(f"/libraries/{lib_id}"), timeout=5).status_code == 204
    assert requests.get(url(f"/libraries/{lib_id}"), timeout=5).status_code == 404


def test_validation_and_conflicts(library):
    assert requests.post(url("/libraries"), json={"name": "No phone"}, timeout=5).status_code == 400
    dup = {**new_library(), "phone": library["phone"]}
    assert requests.post(url("/libraries"), json=dup, timeout=5).status_code == 409


def test_list_is_cached():
    requests.get(url("/libraries?limit=7"), timeout=5)
    r = requests.get(url("/libraries?limit=7"), timeout=5)
    assert r.status_code == 200
    assert r.headers["X-Cache"] in ("HIT", "BYPASS")


def test_holdings_and_branch_catalogue(library, book):
    r = requests.post(url("/holdings"), json={"library_id": library["id"], "book_id": book["id"],
                                              "copies": 2}, timeout=5)
    assert r.status_code == 201
    r = requests.post(url("/holdings"), json={"library_id": library["id"], "book_id": book["id"]}, timeout=5)
    assert r.status_code == 200 and r.json()["copies_total"] == 3

    books = requests.get(url(f"/libraries/{library['id']}/books"), timeout=5).json()
    assert [b["id"] for b in books] == [book["id"]]
    assert books[0]["copies_available"] == 3


def test_issue_and_return_book(library, book, reader):
    requests.post(url("/holdings"), json={"library_id": library["id"], "book_id": book["id"],
                                          "copies": 1}, timeout=5)
    loan_req = {"reader_id": reader["id"], "library_id": library["id"], "book_id": book["id"], "days": 7}

    loan = requests.post(url("/loans"), json=loan_req, timeout=5)
    assert loan.status_code == 201, loan.text
    assert loan.json()["returned_at"] is None

    # the only copy is out
    assert requests.post(url("/loans"), json=loan_req, timeout=5).status_code == 409

    returned = requests.post(url(f"/loans/{loan.json()['id']}/return"), timeout=5)
    assert returned.status_code == 200 and returned.json()["returned_at"] is not None
    assert requests.post(url(f"/loans/{loan.json()['id']}/return"), timeout=5).status_code == 409

    books = requests.get(url(f"/libraries/{library['id']}/books"), timeout=5).json()
    assert books[0]["copies_available"] == 1


def test_author_with_books_cannot_be_deleted(book):
    assert requests.delete(url(f"/authors/{book['author_id']}"), timeout=5).status_code == 409
