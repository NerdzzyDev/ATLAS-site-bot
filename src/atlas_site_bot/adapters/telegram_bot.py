from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from atlas_site_bot.application.formatters import (
    STATUS_LABELS,
    render_dashboard_lead_page,
    render_stats_message,
    render_telegram_message,
)
from atlas_site_bot.application.ports import LeadStats, TelegramMessageRef, TelegramNotifier
from atlas_site_bot.application.use_cases import (
    BuildLeadStatsService,
    HandleLeadActionService,
    ListLeadsService,
)
from atlas_site_bot.domain.enums import LeadAction, LeadStatus
from atlas_site_bot.domain.exceptions import (
    InvalidLeadTransitionError,
    LeadMessageRefNotFoundError,
    LeadNotFoundError,
)
from atlas_site_bot.domain.transitions import available_actions_for_status

logger = logging.getLogger(__name__)

STATUS_CODE_MAP: dict[str, LeadStatus] = {
    "n": LeadStatus.NOT_PROCESSED,
    "p": LeadStatus.IN_PROGRESS,
    "r": LeadStatus.REJECTED,
}
STATUS_TO_CODE = {v: k for k, v in STATUS_CODE_MAP.items()}
ACTION_CODE_MAP: dict[str, LeadAction] = {"a": LeadAction.ACCEPT, "r": LeadAction.REJECT}
ACTION_TO_CODE = {v: k for k, v in ACTION_CODE_MAP.items()}


def _callback_data(action: LeadAction, lead_id: UUID) -> str:
    return f"lead:{action.value}:{lead_id}"


def _parse_callback_data(value: str) -> tuple[LeadAction, UUID]:
    prefix, action_value, lead_id_raw = value.split(":", maxsplit=2)
    if prefix != "lead":
        raise ValueError("Invalid callback prefix")
    return LeadAction(action_value), UUID(lead_id_raw)


def _dash_list_data(status: LeadStatus, offset: int) -> str:
    return f"dash:list:{STATUS_TO_CODE[status]}:{max(offset, 0)}"


def _dash_stats_data(period: str) -> str:
    return f"dash:stats:{period}"


def _dash_action_data(action: LeadAction, lead_id: UUID, status: LeadStatus, offset: int) -> str:
    return (
        f"dact:{ACTION_TO_CODE[action]}:{lead_id}:{STATUS_TO_CODE[status]}:{max(offset, 0)}"
    )


class TelegramBotAdapter(TelegramNotifier):
    def __init__(
        self,
        *,
        token: str,
        chat_ids: list[int],
        site_url: str,
        retry_attempts: int,
        retry_delay_seconds: float,
        action_service: HandleLeadActionService,
        list_service: ListLeadsService,
        stats_service: BuildLeadStatsService,
    ) -> None:
        from telegram.ext import Application, CallbackQueryHandler, CommandHandler

        self._chat_ids = chat_ids
        self._site_url = site_url
        self._retry_attempts = max(retry_attempts, 1)
        self._retry_delay_seconds = max(retry_delay_seconds, 0.0)
        self._action_service = action_service
        self._list_service = list_service
        self._stats_service = stats_service
        self._app = Application.builder().token(token).build()

        self._app.add_handler(CommandHandler("start", self._on_start_command))
        self._app.add_handler(CommandHandler("dashboard", self._on_dashboard_command))
        self._app.add_handler(CallbackQueryHandler(self._on_callback_query))

    @property
    def enabled(self) -> bool:
        return True

    async def start(self) -> None:
        from telegram import BotCommand

        await self._app.initialize()
        await self._app.bot.set_my_commands(
            [
                BotCommand("start", "Показать адрес сайта и меню"),
                BotCommand("dashboard", "Открыть панель заявок"),
            ]
        )
        await self._app.start()
        if self._app.updater is None:
            raise RuntimeError("Telegram updater is not available")
        await self._app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram bot polling started")

    async def stop(self) -> None:
        if self._app.updater is not None:
            await self._app.updater.stop()
        await self._app.stop()
        await self._app.shutdown()
        logger.info("Telegram bot stopped")

    async def send_lead_notification(
        self,
        lead,
        actions,
    ) -> list[TelegramMessageRef]:
        refs: list[TelegramMessageRef] = []
        for chat_id in self._chat_ids:
            try:
                message = await self._with_retry(
                    lambda chat_id=chat_id: self._app.bot.send_message(
                        chat_id=chat_id,
                        text=render_telegram_message(lead),
                        parse_mode="HTML",
                        reply_markup=self._lead_markup(actions, lead.id),
                    ),
                    op_name=f"send lead {lead.id} to chat {chat_id}",
                )
                refs.append(TelegramMessageRef(chat_id=message.chat_id, message_id=message.message_id))
            except Exception as exc:
                logger.exception("Failed to send lead notification", exc_info=exc)
                await self.send_error_alert(
                    f"Ошибка отправки заявки <code>{lead.id}</code> в чат <code>{chat_id}</code>."
                )
        return refs

    async def edit_lead_notifications(self, refs, lead, actions) -> None:
        for ref in refs:
            try:
                await self._with_retry(
                    lambda ref=ref: self._app.bot.edit_message_text(
                        chat_id=ref.chat_id,
                        message_id=ref.message_id,
                        text=render_telegram_message(lead),
                        parse_mode="HTML",
                        reply_markup=self._lead_markup(actions, lead.id),
                    ),
                    op_name=f"edit lead {lead.id} message {ref.chat_id}:{ref.message_id}",
                )
            except Exception as exc:
                logger.exception("Failed to edit lead notification", exc_info=exc)
                await self.send_error_alert(
                    "Ошибка обновления сообщения по заявке "
                    f"<code>{lead.id}</code> (chat <code>{ref.chat_id}</code>, message <code>{ref.message_id}</code>)."
                )

    async def send_error_alert(self, text: str) -> None:
        for chat_id in self._chat_ids:
            try:
                await self._app.bot.send_message(chat_id=chat_id, text=f"⚠️ {text}", parse_mode="HTML")
            except Exception:
                logger.exception("Failed to send error alert to chat %s", chat_id)

    async def _with_retry(
        self,
        fn: Callable[[], Awaitable[Any]],
        *,
        op_name: str,
    ) -> Any:
        last_exc: Exception | None = None
        for attempt in range(1, self._retry_attempts + 1):
            try:
                return await fn()
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning(
                    "Telegram op failed (%s), attempt %s/%s",
                    op_name,
                    attempt,
                    self._retry_attempts,
                    exc_info=exc,
                )
                if attempt < self._retry_attempts and self._retry_delay_seconds > 0:
                    await asyncio.sleep(self._retry_delay_seconds)
        if last_exc is None:
            raise RuntimeError(f"Operation failed without exception: {op_name}")
        raise last_exc

    def _lead_markup(self, actions: list[LeadAction], lead_id: UUID):
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        if not actions:
            return None
        label_map = {LeadAction.ACCEPT: "Принять", LeadAction.REJECT: "Отказать"}
        row = [
            InlineKeyboardButton(
                text=label_map[action],
                callback_data=_callback_data(action, lead_id),
            )
            for action in actions
        ]
        return InlineKeyboardMarkup([row])

    def _dashboard_menu_markup(self):
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "Не обработаны",
                        callback_data=_dash_list_data(LeadStatus.NOT_PROCESSED, 0),
                    ),
                    InlineKeyboardButton(
                        "В работе",
                        callback_data=_dash_list_data(LeadStatus.IN_PROGRESS, 0),
                    ),
                    InlineKeyboardButton(
                        "Отказы",
                        callback_data=_dash_list_data(LeadStatus.REJECTED, 0),
                    ),
                ],
                [
                    InlineKeyboardButton("Статистика: все", callback_data=_dash_stats_data("all")),
                    InlineKeyboardButton("7 дней", callback_data=_dash_stats_data("w")),
                    InlineKeyboardButton("30 дней", callback_data=_dash_stats_data("m")),
                ],
            ]
        )

    def _dashboard_lead_markup(
        self,
        *,
        lead,
        status: LeadStatus,
        offset: int,
        total: int,
    ):
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        rows: list[list[InlineKeyboardButton]] = []

        nav_row: list[InlineKeyboardButton] = []
        if offset > 0:
            nav_row.append(
                InlineKeyboardButton("⬅️", callback_data=_dash_list_data(status, offset - 1))
            )
        if total > 0 and (offset + 1) < total:
            nav_row.append(
                InlineKeyboardButton("➡️", callback_data=_dash_list_data(status, offset + 1))
            )
        if nav_row:
            rows.append(nav_row)

        if lead is not None:
            actions = available_actions_for_status(lead.status)
            if actions:
                rows.append(
                    [
                        InlineKeyboardButton(
                            "Принять" if action == LeadAction.ACCEPT else "Отказать",
                            callback_data=_dash_action_data(action, lead.id, status, offset),
                        )
                        for action in actions
                    ]
                )

        rows.extend(self._dashboard_menu_markup().inline_keyboard)
        return InlineKeyboardMarkup(rows)

    async def _on_start_command(self, update, context) -> None:  # noqa: ANN001
        message = (
            "🤖 <b>ATLAS Site Bot</b>\n"
            "━━━━━━━━━━━━━━\n"
            f"Сайт: <a href=\"{self._site_url}\">{self._site_url}</a>\n\n"
            "Используйте кнопки ниже для просмотра заявок и статистики."
        )
        await update.effective_message.reply_text(
            message,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=self._dashboard_menu_markup(),
        )

    async def _on_dashboard_command(self, update, context) -> None:  # noqa: ANN001
        await self._render_dashboard_list_message(
            message=update.effective_message,
            status=LeadStatus.NOT_PROCESSED,
            offset=0,
            send_new=True,
        )

    async def _on_callback_query(self, update, context) -> None:  # noqa: ANN001
        query = update.callback_query
        if query is None or query.data is None:
            return

        try:
            if query.data.startswith("lead:"):
                await self._handle_notification_action_callback(query)
                return
            if query.data.startswith("dash:"):
                await self._handle_dashboard_callback(query)
                return
            if query.data.startswith("dact:"):
                await self._handle_dashboard_action_callback(query)
                return
            await query.answer("Неизвестная команда", show_alert=True)
        except Exception:
            logger.exception("Unhandled callback error")
            await query.answer("Ошибка обработки", show_alert=True)

    async def _handle_notification_action_callback(self, query) -> None:  # noqa: ANN001
        try:
            action, lead_id = _parse_callback_data(query.data)
            result = await self._action_service.handle(lead_id, action)
            await self.edit_lead_notifications(result.message_refs, result.lead, result.available_actions)
            await query.answer("Статус обновлен")
        except (ValueError, LeadNotFoundError, LeadMessageRefNotFoundError):
            await query.answer("Заявка не найдена", show_alert=True)
        except InvalidLeadTransitionError:
            await query.answer("Переход статуса недоступен", show_alert=True)

    async def _handle_dashboard_callback(self, query) -> None:  # noqa: ANN001
        parts = query.data.split(":")
        if len(parts) < 3:
            await query.answer("Некорректная команда", show_alert=True)
            return
        _, kind, arg = parts[:3]
        if kind == "list":
            if len(parts) != 4:
                await query.answer("Некорректная команда", show_alert=True)
                return
            status = STATUS_CODE_MAP[arg]
            offset = int(parts[3])
            await self._render_dashboard_list_query(query=query, status=status, offset=offset)
            await query.answer()
            return
        if kind == "stats":
            await self._render_stats_query(query=query, period=arg)
            return
        await query.answer("Неизвестный раздел", show_alert=True)

    async def _handle_dashboard_action_callback(self, query) -> None:  # noqa: ANN001
        try:
            _, action_code, lead_id_raw, status_code, offset_raw = query.data.split(":", maxsplit=4)
            action = ACTION_CODE_MAP[action_code]
            lead_id = UUID(lead_id_raw)
            status = STATUS_CODE_MAP[status_code]
            offset = int(offset_raw)
            result = await self._action_service.handle(lead_id, action)
            await self.edit_lead_notifications(result.message_refs, result.lead, result.available_actions)
            await self._render_dashboard_list_query(query=query, status=status, offset=offset)
            await query.answer("Статус обновлен")
        except (KeyError, ValueError, LeadNotFoundError, LeadMessageRefNotFoundError):
            await query.answer("Заявка не найдена", show_alert=True)
        except InvalidLeadTransitionError:
            await query.answer("Переход статуса недоступен", show_alert=True)

    async def _render_dashboard_list_message(
        self,
        *,
        message,
        status: LeadStatus,
        offset: int,
        send_new: bool,
    ) -> None:  # noqa: ANN001
        page = await self._list_service.list_by_status(status, limit=1, offset=offset)
        lead = page.items[0] if page.items else None
        text = render_dashboard_lead_page(
            lead=lead,
            status_label=STATUS_LABELS[status],
            total=page.total,
            position=(page.offset + 1) if lead is not None else None,
        )
        markup = self._dashboard_lead_markup(lead=lead, status=status, offset=page.offset, total=page.total)
        if send_new:
            await message.reply_text(text, parse_mode="HTML", reply_markup=markup)
        else:
            await message.edit_text(text, parse_mode="HTML", reply_markup=markup)

    async def _render_dashboard_list_query(self, *, query, status: LeadStatus, offset: int) -> None:  # noqa: ANN001
        page = await self._list_service.list_by_status(status, limit=1, offset=offset)
        lead = page.items[0] if page.items else None
        text = render_dashboard_lead_page(
            lead=lead,
            status_label=STATUS_LABELS[status],
            total=page.total,
            position=(page.offset + 1) if lead is not None else None,
        )
        markup = self._dashboard_lead_markup(lead=lead, status=status, offset=page.offset, total=page.total)
        await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=markup)

    async def _render_stats_query(self, *, query, period: str) -> None:  # noqa: ANN001
        stats: LeadStats
        if period == "all":
            stats = await self._stats_service.all_time()
        elif period == "w":
            stats = await self._stats_service.last_week()
        elif period == "m":
            stats = await self._stats_service.last_month()
        else:
            await query.answer("Неизвестный период", show_alert=True)
            return

        await query.edit_message_text(
            text=render_stats_message(stats),
            parse_mode="HTML",
            reply_markup=self._dashboard_menu_markup(),
        )
        await query.answer()


class NullTelegramNotifier(TelegramNotifier):
    @property
    def enabled(self) -> bool:
        return False

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def send_lead_notification(self, lead, actions) -> list[TelegramMessageRef]:
        return []

    async def edit_lead_notifications(self, refs, lead, actions) -> None:
        return None

    async def send_error_alert(self, text: str) -> None:
        return None
