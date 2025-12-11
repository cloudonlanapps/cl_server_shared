"""Shared database models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


from .job import Job
from .queue import QueueEntry

__all__ = ["Base", "Job", "QueueEntry"]
