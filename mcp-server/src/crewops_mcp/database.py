"""A lazily opened SQLAlchemy connection pool scoped to the application."""

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


class Database:
    def __init__(self, url: str | None) -> None:
        self.url = url
        self._engine: Engine | None = None

    def connect(self):
        if not self.url:
            raise RuntimeError("DATABASE_URL is not configured")
        if self._engine is None:
            self._engine = create_engine(self.url, future=True)
        return self._engine.connect()

    def dispose(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
