"""Domain enums, stored as VARCHAR + CHECK constraints (no native PG enum
types, so adding values later is a plain ALTER instead of an enum migration).
"""

from enum import StrEnum

from sqlalchemy import Enum as SAEnum


class PreferredLanguage(StrEnum):
    EN = "en"
    ROMAN_URDU = "roman_urdu"
    UR = "ur"


class ConversationStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class MessageDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class SenderType(StrEnum):
    CUSTOMER = "customer"
    BOT = "bot"
    AGENT = "agent"


class ContentType(StrEnum):
    TEXT = "text"
    VOICE = "voice"
    IMAGE = "image"
    PDF = "pdf"
    LOCATION = "location"


class LeadSource(StrEnum):
    BOT = "bot"
    MANUAL = "manual"


class InterestType(StrEnum):
    ROOM = "room"
    EVENT_WEDDING = "event_wedding"
    CORPORATE = "corporate"
    DAY_TRIP = "day_trip"
    OTHER = "other"


class LeadStage(StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    BOOKING_SENT = "booking_sent"
    WON = "won"
    LOST = "lost"


class UserRole(StrEnum):
    ADMIN = "admin"
    AGENT = "agent"


class MediaPurpose(StrEnum):
    ROOM_PHOTO = "room_photo"
    RATE_CARD = "rate_card"
    LOCATION = "location"
    OTHER = "other"


def db_enum(enum_cls: type[StrEnum], name: str) -> SAEnum:
    """VARCHAR-backed enum column type with a CHECK constraint."""
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        length=32,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda cls: [member.value for member in cls],
    )
