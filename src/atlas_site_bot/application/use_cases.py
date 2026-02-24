from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from atlas_site_bot.application.ports import (
    LeadStats,
    LeadMessageRefRepository,
    LeadRepository,
    TelegramMessageRef,
    TelegramNotifier,
)
from atlas_site_bot.domain.enums import FormType, LeadAction
from atlas_site_bot.domain.exceptions import (
    LeadNotFoundError,
)
from atlas_site_bot.domain.models import LeadSubmission
from atlas_site_bot.domain.transitions import available_actions_for_status, transition_status


@dataclass(frozen=True, slots=True)
class SubmitLeadCommand:
    task: str
    form_type: FormType
    fio: str
    email: str
    phone: str
    company: str


@dataclass(frozen=True, slots=True)
class LeadActionResult:
    lead: LeadSubmission
    message_refs: list[TelegramMessageRef]
    available_actions: list[LeadAction]


class SubmitLeadService:
    def __init__(
        self,
        lead_repo: LeadRepository,
        ref_repo: LeadMessageRefRepository,
        notifier: TelegramNotifier,
    ) -> None:
        self._lead_repo = lead_repo
        self._ref_repo = ref_repo
        self._notifier = notifier

    async def submit(self, command: SubmitLeadCommand) -> LeadSubmission:
        lead = LeadSubmission.create(
            task=command.task,
            form_type=command.form_type,
            fio=command.fio,
            email=command.email,
            phone=command.phone,
            company=command.company,
        )
        await self._lead_repo.save(lead)
        actions = available_actions_for_status(lead.status)
        message_refs = await self._notifier.send_lead_notification(lead, actions)
        await self._ref_repo.save_many(lead.id, message_refs)
        return lead


class HandleLeadActionService:
    def __init__(
        self,
        lead_repo: LeadRepository,
        ref_repo: LeadMessageRefRepository,
    ) -> None:
        self._lead_repo = lead_repo
        self._ref_repo = ref_repo

    async def handle(self, lead_id: UUID, action: LeadAction) -> LeadActionResult:
        lead = await self._lead_repo.get(lead_id)
        if lead is None:
            raise LeadNotFoundError(str(lead_id))

        message_refs = await self._ref_repo.list_by_lead(lead_id)
        next_status = transition_status(lead.status, action)
        updated = lead.with_status(next_status)
        await self._lead_repo.save(updated)

        return LeadActionResult(
            lead=updated,
            message_refs=message_refs,
            available_actions=available_actions_for_status(updated.status),
        )


@dataclass(frozen=True, slots=True)
class LeadListPage:
    items: list[LeadSubmission]
    total: int
    offset: int
    limit: int
    status: LeadStatus


class ListLeadsService:
    def __init__(self, lead_repo: LeadRepository) -> None:
        self._lead_repo = lead_repo

    async def list_by_status(
        self,
        status: LeadStatus,
        *,
        limit: int = 1,
        offset: int = 0,
    ) -> LeadListPage:
        safe_offset = max(offset, 0)
        total = await self._lead_repo.count_by_status(status)
        if total and safe_offset >= total:
            safe_offset = max(total - 1, 0)
        items = await self._lead_repo.list_by_status(status, limit=limit, offset=safe_offset)
        return LeadListPage(
            items=items,
            total=total,
            offset=safe_offset,
            limit=limit,
            status=status,
        )


class BuildLeadStatsService:
    def __init__(self, lead_repo: LeadRepository) -> None:
        self._lead_repo = lead_repo

    async def all_time(self) -> LeadStats:
        return await self._lead_repo.build_stats(since=None, period_label="За все время")

    async def last_week(self, now: datetime | None = None) -> LeadStats:
        base = now or datetime.now(timezone.utc)
        return await self._lead_repo.build_stats(
            since=base - timedelta(days=7),
            period_label="За 7 дней",
        )

    async def last_month(self, now: datetime | None = None) -> LeadStats:
        base = now or datetime.now(timezone.utc)
        return await self._lead_repo.build_stats(
            since=base - timedelta(days=30),
            period_label="За 30 дней",
        )
