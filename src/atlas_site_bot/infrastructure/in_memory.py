from __future__ import annotations

import asyncio
from datetime import datetime
from uuid import UUID

from atlas_site_bot.application.ports import (
    LeadMessageRefRepository,
    LeadRepository,
    LeadStats,
    TelegramMessageRef,
)
from atlas_site_bot.domain.enums import LeadStatus
from atlas_site_bot.domain.models import LeadSubmission


class InMemoryLeadRepository(LeadRepository):
    def __init__(self) -> None:
        self._items: dict[UUID, LeadSubmission] = {}
        self._lock = asyncio.Lock()

    async def save(self, lead: LeadSubmission) -> None:
        async with self._lock:
            self._items[lead.id] = lead

    async def get(self, lead_id: UUID) -> LeadSubmission | None:
        async with self._lock:
            return self._items.get(lead_id)

    async def list_by_status(
        self,
        status: LeadStatus,
        *,
        limit: int,
        offset: int,
    ) -> list[LeadSubmission]:
        async with self._lock:
            filtered = [item for item in self._items.values() if item.status == status]
            filtered.sort(key=lambda x: x.created_at, reverse=True)
            return filtered[offset : offset + limit]

    async def count_by_status(self, status: LeadStatus) -> int:
        async with self._lock:
            return sum(1 for item in self._items.values() if item.status == status)

    async def build_stats(self, *, since: datetime | None, period_label: str) -> LeadStats:
        async with self._lock:
            items = list(self._items.values())
            if since is not None:
                items = [item for item in items if item.created_at >= since]
            return LeadStats(
                total=len(items),
                not_processed=sum(1 for i in items if i.status == LeadStatus.NOT_PROCESSED),
                in_progress=sum(1 for i in items if i.status == LeadStatus.IN_PROGRESS),
                rejected=sum(1 for i in items if i.status == LeadStatus.REJECTED),
                period_label=period_label,
                since=since,
            )


class InMemoryLeadMessageRefRepository(LeadMessageRefRepository):
    def __init__(self) -> None:
        self._items: dict[UUID, list[TelegramMessageRef]] = {}
        self._lock = asyncio.Lock()

    async def save_many(self, lead_id: UUID, refs: list[TelegramMessageRef]) -> None:
        async with self._lock:
            self._items[lead_id] = list(refs)

    async def list_by_lead(self, lead_id: UUID) -> list[TelegramMessageRef]:
        async with self._lock:
            return list(self._items.get(lead_id, []))
