from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from atlas_site_bot.application.ports import LeadMessageRefRepository, LeadRepository, LeadStats, TelegramMessageRef
from atlas_site_bot.domain.enums import FormType, LeadStatus
from atlas_site_bot.domain.models import LeadSubmission


class Base(DeclarativeBase):
    pass


class LeadRow(Base):
    __tablename__ = "leads"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    task: Mapped[str] = mapped_column(Text, nullable=False)
    form_type: Mapped[str] = mapped_column(String(64), nullable=False)
    fio: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    phone: Mapped[str] = mapped_column(String(50), nullable=False)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class LeadMessageRefRow(Base):
    __tablename__ = "lead_message_refs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    lead_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class Database:
    def __init__(self, database_url: str) -> None:
        self.engine: AsyncEngine = create_async_engine(database_url, pool_pre_ping=True)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            yield session

    async def create_schema(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def dispose(self) -> None:
        await self.engine.dispose()


def _to_domain(row: LeadRow) -> LeadSubmission:
    return LeadSubmission(
        id=row.id,
        task=row.task,
        form_type=FormType(row.form_type),
        fio=row.fio,
        email=row.email,
        phone=row.phone,
        company=row.company,
        status=LeadStatus(row.status),
        created_at=row.created_at,
    )


class PostgresLeadRepository(LeadRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def save(self, lead: LeadSubmission) -> None:
        async with self._db.session() as session:
            row = await session.get(LeadRow, lead.id)
            if row is None:
                row = LeadRow(
                    id=lead.id,
                    task=lead.task,
                    form_type=lead.form_type.value,
                    fio=lead.fio,
                    email=lead.email,
                    phone=lead.phone,
                    company=lead.company,
                    status=lead.status.value,
                    created_at=lead.created_at,
                )
                session.add(row)
            else:
                row.task = lead.task
                row.form_type = lead.form_type.value
                row.fio = lead.fio
                row.email = lead.email
                row.phone = lead.phone
                row.company = lead.company
                row.status = lead.status.value
            await session.commit()

    async def get(self, lead_id: UUID) -> LeadSubmission | None:
        async with self._db.session() as session:
            row = await session.get(LeadRow, lead_id)
            return _to_domain(row) if row is not None else None

    async def list_by_status(
        self,
        status: LeadStatus,
        *,
        limit: int,
        offset: int,
    ) -> list[LeadSubmission]:
        async with self._db.session() as session:
            stmt = (
                select(LeadRow)
                .where(LeadRow.status == status.value)
                .order_by(LeadRow.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [_to_domain(row) for row in rows]

    async def count_by_status(self, status: LeadStatus) -> int:
        async with self._db.session() as session:
            stmt = select(func.count()).select_from(LeadRow).where(LeadRow.status == status.value)
            return int((await session.execute(stmt)).scalar_one())

    async def build_stats(self, *, since: datetime | None, period_label: str) -> LeadStats:
        async with self._db.session() as session:
            conditions: list[Any] = []
            if since is not None:
                conditions.append(LeadRow.created_at >= since)

            def _count_stmt(status: LeadStatus | None = None):
                stmt = select(func.count()).select_from(LeadRow)
                for condition in conditions:
                    stmt = stmt.where(condition)
                if status is not None:
                    stmt = stmt.where(LeadRow.status == status.value)
                return stmt

            total = int((await session.execute(_count_stmt())).scalar_one())
            not_processed = int((await session.execute(_count_stmt(LeadStatus.NOT_PROCESSED))).scalar_one())
            in_progress = int((await session.execute(_count_stmt(LeadStatus.IN_PROGRESS))).scalar_one())
            rejected = int((await session.execute(_count_stmt(LeadStatus.REJECTED))).scalar_one())
            return LeadStats(
                total=total,
                not_processed=not_processed,
                in_progress=in_progress,
                rejected=rejected,
                period_label=period_label,
                since=since,
            )


class PostgresLeadMessageRefRepository(LeadMessageRefRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def save_many(self, lead_id: UUID, refs: list[TelegramMessageRef]) -> None:
        async with self._db.session() as session:
            rows = [
                LeadMessageRefRow(lead_id=lead_id, chat_id=ref.chat_id, message_id=ref.message_id)
                for ref in refs
            ]
            session.add_all(rows)
            await session.commit()

    async def list_by_lead(self, lead_id: UUID) -> list[TelegramMessageRef]:
        async with self._db.session() as session:
            stmt = (
                select(LeadMessageRefRow)
                .where(LeadMessageRefRow.lead_id == lead_id)
                .order_by(LeadMessageRefRow.id.asc())
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [TelegramMessageRef(chat_id=row.chat_id, message_id=row.message_id) for row in rows]
