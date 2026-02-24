from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from atlas_site_bot.domain.enums import LeadAction, LeadStatus
from atlas_site_bot.domain.models import LeadSubmission


@dataclass(frozen=True, slots=True)
class TelegramMessageRef:
    chat_id: int
    message_id: int


@dataclass(frozen=True, slots=True)
class LeadStats:
    total: int
    not_processed: int
    in_progress: int
    rejected: int
    period_label: str
    since: datetime | None = None


class LeadRepository(Protocol):
    async def save(self, lead: LeadSubmission) -> None: ...

    async def get(self, lead_id: UUID) -> LeadSubmission | None: ...

    async def list_by_status(
        self,
        status: LeadStatus,
        *,
        limit: int,
        offset: int,
    ) -> list[LeadSubmission]: ...

    async def count_by_status(self, status: LeadStatus) -> int: ...

    async def build_stats(self, *, since: datetime | None, period_label: str) -> LeadStats: ...


class LeadMessageRefRepository(Protocol):
    async def save_many(self, lead_id: UUID, refs: list[TelegramMessageRef]) -> None: ...

    async def list_by_lead(self, lead_id: UUID) -> list[TelegramMessageRef]: ...


class TelegramNotifier(Protocol):
    async def send_lead_notification(
        self,
        lead: LeadSubmission,
        actions: list[LeadAction],
    ) -> list[TelegramMessageRef]: ...

    async def edit_lead_notifications(
        self,
        refs: list[TelegramMessageRef],
        lead: LeadSubmission,
        actions: list[LeadAction],
    ) -> None: ...

    async def send_error_alert(self, text: str) -> None: ...
