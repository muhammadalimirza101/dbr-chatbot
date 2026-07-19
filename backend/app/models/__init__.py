"""ORM models. Importing this package registers every table on Base.metadata
(required by Alembic autogenerate and relationship resolution).
"""

from app.models.audit import AuditLog
from app.models.conversation import Conversation, Message
from app.models.customer import Customer
from app.models.kb import KnowledgeBase, UnansweredQuestion
from app.models.lead import Lead
from app.models.media import MediaAsset
from app.models.user import User
from app.models.wa_auth import WAAuthState

__all__ = [
    "AuditLog",
    "Conversation",
    "Customer",
    "KnowledgeBase",
    "Lead",
    "MediaAsset",
    "Message",
    "UnansweredQuestion",
    "User",
    "WAAuthState",
]
