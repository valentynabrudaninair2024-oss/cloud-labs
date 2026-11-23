"""Blog REST API: authors and posts, stored in PostgreSQL."""
import os
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import DateTime, ForeignKey, String, Text, create_engine, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

DB_URL = (
    f"postgresql+psycopg://{os.environ['DB_USER']}:{os.environ['DB_PASSWORD']}"
    f"@{os.environ['DB_HOST']}:{os.environ.get('DB_PORT', '5432')}/{os.environ['DB_NAME']}"
)
engine = create_engine(DB_URL, pool_pre_ping=True, pool_size=5, max_overflow=10)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class Author(Base):
    __tablename__ = "authors"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(200), unique=True)


class Post(Base):
    __tablename__ = "posts"
    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("authors.id"))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class AuthorIn(BaseModel):
    name: str
    email: str


class AuthorOut(AuthorIn):
    id: int
    model_config = {"from_attributes": True}


class PostIn(BaseModel):
    author_id: int
    title: str
    body: str


class PostOut(PostIn):
    id: int
    created_at: datetime
    model_config = {"from_attributes": True}


app = FastAPI(title="Cloud Labs Blog API")


@app.on_event("startup")
def init_db() -> None:
    Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.post("/authors", response_model=AuthorOut, status_code=201)
def create_author(data: AuthorIn, db: Session = Depends(get_db)):
    author = Author(**data.model_dump())
    db.add(author)
    db.commit()
    db.refresh(author)
    return author


@app.get("/authors", response_model=list[AuthorOut])
def list_authors(db: Session = Depends(get_db)):
    return db.scalars(select(Author).order_by(Author.id)).all()


@app.get("/authors/{author_id}", response_model=AuthorOut)
def get_author(author_id: int, db: Session = Depends(get_db)):
    author = db.get(Author, author_id)
    if author is None:
        raise HTTPException(404, "Author not found")
    return author


@app.post("/posts", response_model=PostOut, status_code=201)
def create_post(data: PostIn, db: Session = Depends(get_db)):
    if db.get(Author, data.author_id) is None:
        raise HTTPException(404, "Author not found")
    post = Post(**data.model_dump())
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


@app.get("/posts", response_model=list[PostOut])
def list_posts(limit: int = 20, db: Session = Depends(get_db)):
    return db.scalars(select(Post).order_by(Post.id.desc()).limit(limit)).all()


@app.get("/posts/{post_id}", response_model=PostOut)
def get_post(post_id: int, db: Session = Depends(get_db)):
    post = db.get(Post, post_id)
    if post is None:
        raise HTTPException(404, "Post not found")
    return post
