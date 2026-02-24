from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from uuid import UUID, uuid4

from atlas_site_bot.domain.enums import FormType, LeadStatus


@dataclass(frozen=True, slots=True)
class LeadSubmission:
    id: UUID
    task: str
    form_type: FormType
    fio: str
    email: str
    phone: str
    company: str
    status: LeadStatus
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        task: str,
        form_type: FormType,
        fio: str,
        email: str,
        phone: str,
        company: str,
    ) -> "LeadSubmission":
        return cls(
            id=uuid4(),
            task=task,
            form_type=form_type,
            fio=fio,
            email=email,
            phone=phone,
            company=company,
            status=LeadStatus.NOT_PROCESSED,
            created_at=datetime.now(timezone.utc),
        )

    def with_status(self, status: LeadStatus) -> "LeadSubmission":
        return replace(self, status=status)

