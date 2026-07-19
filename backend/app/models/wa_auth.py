from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class WAAuthState(Base):
    """Baileys session material (creds + signal keys), keyed by name.

    Values are opaque BufferJSON strings owned by the connector. This data
    grants full control of the WhatsApp number — it is exposed only through
    the shared-secret /internal endpoints, never to dashboard users.
    """

    __tablename__ = "wa_auth_state"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
