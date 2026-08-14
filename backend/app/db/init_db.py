from app.db.session import Base, engine
from app.models import Job  # noqa: F401


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
