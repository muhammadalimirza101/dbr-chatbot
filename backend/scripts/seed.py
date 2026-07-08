"""Seed the database: one admin user + starter KB entries for DBR.

Usage (from backend/, with the venv python):
    $env:SEED_ADMIN_EMAIL = "admin@example.com"
    $env:SEED_ADMIN_PASSWORD = "<strong password, min 10 chars>"
    .\\.venv\\Scripts\\python -m scripts.seed

- Admin credentials come from env vars only (never files/argv). If they are
  unset, the admin step is skipped with a warning.
- KB entries are idempotent (matched by question text) and embedded via
  OpenAI at insert time.
- Every price/timing/package detail that must come from the client is a
  TODO placeholder — edit these in the dashboard KB manager before launch.
"""

import asyncio
import os
import sys

from sqlalchemy import select

from app.database import async_session_factory, engine
from app.models import KnowledgeBase, User
from app.models.enums import UserRole
from app.services.auth import hash_password
from app.services.embeddings import embed_text

# (question, answer, category) — answers with TODO must be completed by staff
KB_ENTRIES: list[tuple[str, str, str]] = [
    (
        "What room types do you have?",
        "We offer comfortable rooms right by the beach at Manora. "
        "TODO: list exact room categories (standard/deluxe/family, AC, occupancy).",
        "rooms",
    ),
    (
        "Do you have rooms with a sea view?",
        "Yes — several rooms face the beach with sea views. "
        "TODO: confirm which categories have sea view.",
        "rooms",
    ),
    (
        "What are the check-in and check-out times?",
        "TODO: exact check-in and check-out times (e.g. check-in 2 PM, check-out 12 PM).",
        "rooms",
    ),
    (
        "How much does a room cost per night?",
        "Room rates depend on the room type, dates, and season. Our reservations team "
        "confirms the exact rate for your dates before any booking. "
        "TODO: attach current rate card once finalized.",
        "rooms",
    ),
    (
        "How do I reach the resort on Manora Island?",
        "You can take the ferry from Keamari Jetty in Karachi — the crossing takes about "
        "10–15 minutes and the resort is a short distance from Manora jetty. Manora is also "
        "reachable by road via the Manora causeway from Mauripur. "
        "TODO: confirm pickup/directions details from the jetty.",
        "transport",
    ),
    (
        "What are the ferry timings from Keamari?",
        "TODO: exact ferry timings and fare from Keamari to Manora.",
        "transport",
    ),
    (
        "Is there parking if I come by road?",
        "TODO: parking availability and charges at or near the resort.",
        "transport",
    ),
    (
        "Do you have a restaurant? What food do you serve?",
        "Yes, we serve food at the resort and all food is halal. "
        "TODO: restaurant name, cuisine, menu highlights, and timings.",
        "dining",
    ),
    (
        "Can we bring our own food?",
        "TODO: outside-food policy (allowed / not allowed / corkage-style charges).",
        "dining",
    ),
    (
        "Do you host weddings and mehndi events?",
        "We'd love to host your big day! DBR arranges beach-side weddings and private "
        "events with the sea as your backdrop. Our events team prepares a custom package — "
        "share your dates and expected guests and we'll take it from there. "
        "TODO: capacity, packages, and what's included.",
        "events",
    ),
    (
        "Can you host corporate events or company trips?",
        "Yes — we host corporate retreats, team outings, and day-long company events. "
        "Our team will build a package around your group size and program. "
        "TODO: hall/space capacity, AV facilities, corporate packages.",
        "events",
    ),
    (
        "What is included in the day trip package?",
        "Our day trips cover beach access and use of resort facilities for the day. "
        "TODO: exact inclusions (meals? water sports?), timings, and per-person price.",
        "activities",
    ),
    (
        "What water sports do you offer?",
        "We offer beach water sports including jet ski, banana boat rides, and more. "
        "TODO: confirm the current activity list, timings, and prices.",
        "activities",
    ),
    (
        "Is the resort family friendly? Can we come with kids?",
        "Absolutely — families are very welcome, and the beach is a hit with kids. "
        "TODO: any kids' facilities, lifeguard/safety notes, family-section details.",
        "general",
    ),
    (
        "Is swimming in the sea allowed? Is it safe?",
        "TODO: swimming policy, safe timings/seasons, and lifeguard availability.",
        "general",
    ),
    (
        "How do I book a room?",
        "Just share your dates, number of guests, and preferred room type here on WhatsApp — "
        "our reservations team will confirm availability and complete your booking. "
        "TODO: advance/deposit policy if any.",
        "general",
    ),
]


async def seed_admin() -> None:
    email = os.getenv("SEED_ADMIN_EMAIL", "").strip().lower()
    password = os.getenv("SEED_ADMIN_PASSWORD", "")
    if not email or not password:
        print("SEED_ADMIN_EMAIL / SEED_ADMIN_PASSWORD not set — skipping admin creation.")
        print("(You can also use: python -m scripts.create_admin <email> \"<name>\")")
        return
    if len(password) < 10:
        print("SEED_ADMIN_PASSWORD must be at least 10 characters.")
        sys.exit(1)
    async with async_session_factory() as session:
        existing = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if existing:
            print(f"admin {email} already exists — leaving it untouched.")
            return
        session.add(
            User(
                email=email,
                password_hash=hash_password(password),
                full_name="DBR Admin",
                role=UserRole.ADMIN,
            )
        )
        await session.commit()
        print(f"admin created: {email}")


async def seed_kb() -> None:
    async with async_session_factory() as session:
        created = skipped = 0
        for question, answer, category in KB_ENTRIES:
            exists = (
                await session.execute(
                    select(KnowledgeBase.id).where(KnowledgeBase.question == question)
                )
            ).first()
            if exists:
                skipped += 1
                continue
            session.add(
                KnowledgeBase(
                    question=question,
                    answer=answer,
                    category=category,
                    embedding=await embed_text(question),
                )
            )
            created += 1
        await session.commit()
        print(f"KB seed: {created} created, {skipped} already present.")
        todo_count = sum(1 for _, answer, _ in KB_ENTRIES if "TODO" in answer)
        print(f"NOTE: {todo_count} entries contain TODO placeholders — fill them in the "
              "dashboard (Knowledge Base) with real details from the client.")


async def main() -> None:
    await seed_admin()
    await seed_kb()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
