"""SQLAlchemy models. Importing this package registers all tables on Base.metadata."""

from app.models.admin import Admin
from app.models.answer import Answer
from app.models.base import Base
from app.models.candidate import Candidate
from app.models.enums import AdminRole, EventType, ExamStatus, SessionStatus, SittingStatus
from app.models.event import ExamEvent
from app.models.exam import Exam
from app.models.license import SystemLicense
from app.models.room import Room
from app.models.session import ExamSession
from app.models.sitting import Sitting

__all__ = [
    "Base",
    "Admin",
    "Answer",
    "Candidate",
    "Exam",
    "ExamEvent",
    "ExamSession",
    "Room",
    "Sitting",
    "SystemLicense",
    "AdminRole",
    "EventType",
    "ExamStatus",
    "SessionStatus",
    "SittingStatus",
]
