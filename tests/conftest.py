import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")


def url(path):
    return f"{BASE_URL}{path}"


def unique():
    return uuid.uuid4().hex[:10]


def new_library():
    return {"name": f"Test library {unique()}", "address": "вул. Тестова, 1",
            "city": "Львів", "phone": f"+38{uuid.uuid4().int % 10**10:010d}"}


@pytest.fixture
def library():
    r = requests.post(url("/libraries"), json=new_library(), timeout=5)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def book():
    author = requests.post(url("/authors"), json={"full_name": f"Author {unique()}"}, timeout=5).json()
    genre = requests.post(url("/genres"), json={"name": f"Genre {unique()}"}, timeout=5).json()
    r = requests.post(url("/books"), json={"title": f"Book {unique()}", "isbn": unique(),
                                           "year": 2020, "author_id": author["id"],
                                           "genre_id": genre["id"]}, timeout=5)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def reader():
    r = requests.post(url("/readers"), json={"full_name": "Test Reader",
                                             "email": f"{unique()}@example.com"}, timeout=5)
    assert r.status_code == 201, r.text
    return r.json()
