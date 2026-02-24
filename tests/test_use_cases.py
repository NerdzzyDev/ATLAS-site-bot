import pytest

from atlas_site_bot.application.ports import TelegramMessageRef
from atlas_site_bot.application.use_cases import (
    BuildLeadStatsService,
    HandleLeadActionService,
    ListLeadsService,
    SubmitLeadCommand,
    SubmitLeadService,
)
from atlas_site_bot.domain.enums import FormType, LeadAction, LeadStatus
from atlas_site_bot.domain.exceptions import InvalidLeadTransitionError
from atlas_site_bot.infrastructure.in_memory import (
    InMemoryLeadMessageRefRepository,
    InMemoryLeadRepository,
)


class FakeNotifier:
    def __init__(self) -> None:
        self.sent = []
        self.edited = []

    async def send_lead_notification(self, lead, actions):  # noqa: ANN001
        self.sent.append((lead, actions))
        return [TelegramMessageRef(chat_id=111, message_id=222)]

    async def edit_lead_notifications(self, refs, lead, actions):  # noqa: ANN001
        self.edited.append((refs, lead, actions))

    async def send_error_alert(self, text: str) -> None:
        return None


@pytest.mark.asyncio
async def test_submit_lead_creates_new_lead_and_stores_message_ref() -> None:
    lead_repo = InMemoryLeadRepository()
    ref_repo = InMemoryLeadMessageRefRepository()
    notifier = FakeNotifier()
    service = SubmitLeadService(lead_repo, ref_repo, notifier)

    lead = await service.submit(
        SubmitLeadCommand(
            task="Нужен аудит сайта",
            form_type=FormType.MAIN_PAGE,
            fio="Иван Иванов",
            email="ivan@example.com",
            phone="+79990000000",
            company="ATLAS",
        )
    )

    assert lead.status == LeadStatus.NOT_PROCESSED
    stored = await lead_repo.get(lead.id)
    assert stored is not None
    refs = await ref_repo.list_by_lead(lead.id)
    assert refs == [TelegramMessageRef(chat_id=111, message_id=222)]
    assert notifier.sent


@pytest.mark.asyncio
async def test_lead_actions_change_status_without_db() -> None:
    lead_repo = InMemoryLeadRepository()
    ref_repo = InMemoryLeadMessageRefRepository()
    notifier = FakeNotifier()
    submit_service = SubmitLeadService(lead_repo, ref_repo, notifier)
    action_service = HandleLeadActionService(lead_repo, ref_repo)

    lead = await submit_service.submit(
        SubmitLeadCommand(
            task="Позвоните завтра",
            form_type=FormType.MAIN_PAGE,
            fio="Петр Петров",
            email="petr@example.com",
            phone="+78880000000",
            company="ООО Ромашка",
        )
    )

    accepted = await action_service.handle(lead.id, LeadAction.ACCEPT)
    assert accepted.lead.status == LeadStatus.IN_PROGRESS
    assert accepted.available_actions == [LeadAction.REJECT]
    assert accepted.message_refs == [TelegramMessageRef(chat_id=111, message_id=222)]

    rejected = await action_service.handle(lead.id, LeadAction.REJECT)
    assert rejected.lead.status == LeadStatus.REJECTED
    assert rejected.available_actions == []


@pytest.mark.asyncio
async def test_invalid_transition_raises() -> None:
    lead_repo = InMemoryLeadRepository()
    ref_repo = InMemoryLeadMessageRefRepository()
    notifier = FakeNotifier()
    submit_service = SubmitLeadService(lead_repo, ref_repo, notifier)
    action_service = HandleLeadActionService(lead_repo, ref_repo)

    lead = await submit_service.submit(
        SubmitLeadCommand(
            task="Тест",
            form_type=FormType.MAIN_PAGE,
            fio="Тест",
            email="test@example.com",
            phone="123",
            company="Тест",
        )
    )
    await action_service.handle(lead.id, LeadAction.REJECT)

    with pytest.raises(InvalidLeadTransitionError):
        await action_service.handle(lead.id, LeadAction.ACCEPT)


@pytest.mark.asyncio
async def test_list_by_status_and_stats() -> None:
    lead_repo = InMemoryLeadRepository()
    ref_repo = InMemoryLeadMessageRefRepository()
    notifier = FakeNotifier()
    submit_service = SubmitLeadService(lead_repo, ref_repo, notifier)
    action_service = HandleLeadActionService(lead_repo, ref_repo)
    list_service = ListLeadsService(lead_repo)
    stats_service = BuildLeadStatsService(lead_repo)

    lead1 = await submit_service.submit(
        SubmitLeadCommand(
            task="A",
            form_type=FormType.MAIN_PAGE,
            fio="A",
            email="a@example.com",
            phone="1",
            company="A",
        )
    )
    lead2 = await submit_service.submit(
        SubmitLeadCommand(
            task="B",
            form_type=FormType.MAIN_PAGE,
            fio="B",
            email="b@example.com",
            phone="2",
            company="B",
        )
    )
    await action_service.handle(lead2.id, LeadAction.ACCEPT)

    page = await list_service.list_by_status(LeadStatus.NOT_PROCESSED, limit=10, offset=0)
    assert page.total == 1
    assert page.items[0].id == lead1.id

    stats = await stats_service.all_time()
    assert stats.total == 2
    assert stats.not_processed == 1
    assert stats.in_progress == 1
    assert stats.rejected == 0
