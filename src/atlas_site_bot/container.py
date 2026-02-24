from __future__ import annotations

from atlas_site_bot.adapters.telegram_bot import NullTelegramNotifier, TelegramBotAdapter
from atlas_site_bot.application.use_cases import (
    BuildLeadStatsService,
    HandleLeadActionService,
    ListLeadsService,
    SubmitLeadService,
)
from atlas_site_bot.infrastructure.in_memory import (
    InMemoryLeadMessageRefRepository,
    InMemoryLeadRepository,
)
from atlas_site_bot.infrastructure.postgres import (
    Database,
    PostgresLeadMessageRefRepository,
    PostgresLeadRepository,
)
from atlas_site_bot.settings import Settings


class ApplicationContainer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db: Database | None = None
        if settings.database_url:
            self.db = Database(settings.database_url)
            self.lead_repo = PostgresLeadRepository(self.db)
            self.ref_repo = PostgresLeadMessageRefRepository(self.db)
        else:
            self.lead_repo = InMemoryLeadRepository()
            self.ref_repo = InMemoryLeadMessageRefRepository()

        self.handle_action_service = HandleLeadActionService(self.lead_repo, self.ref_repo)
        self.list_leads_service = ListLeadsService(self.lead_repo)
        self.stats_service = BuildLeadStatsService(self.lead_repo)

        if (
            settings.telegram_enabled
            and settings.telegram_bot_token
            and settings.telegram_chat_ids
        ):
            self.telegram_notifier = TelegramBotAdapter(
                token=settings.telegram_bot_token,
                chat_ids=settings.telegram_chat_ids,
                site_url=settings.site_url,
                retry_attempts=settings.telegram_retry_attempts,
                retry_delay_seconds=settings.telegram_retry_delay_seconds,
                action_service=self.handle_action_service,
                list_service=self.list_leads_service,
                stats_service=self.stats_service,
            )
        else:
            self.telegram_notifier = NullTelegramNotifier()

        self.submit_lead_service = SubmitLeadService(
            self.lead_repo,
            self.ref_repo,
            self.telegram_notifier,
        )

    async def start(self) -> None:
        if self.db is not None:
            await self.db.create_schema()
        if hasattr(self.telegram_notifier, "start"):
            await self.telegram_notifier.start()

    async def stop(self) -> None:
        if hasattr(self.telegram_notifier, "stop"):
            await self.telegram_notifier.stop()
        if self.db is not None:
            await self.db.dispose()
