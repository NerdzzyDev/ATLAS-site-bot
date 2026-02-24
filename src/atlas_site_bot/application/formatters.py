from datetime import timezone

from atlas_site_bot.application.ports import LeadStats
from atlas_site_bot.domain.enums import FormType, LeadStatus
from atlas_site_bot.domain.models import LeadSubmission

STATUS_LABELS: dict[LeadStatus, str] = {
    LeadStatus.NOT_PROCESSED: "Заявка не обработана",
    LeadStatus.IN_PROGRESS: "В работе",
    LeadStatus.REJECTED: "Обработана: отказ",
}

FORM_TYPE_LABELS: dict[FormType, str] = {
    FormType.MAIN_PAGE: "Главная страница",
}


def render_telegram_message(lead: LeadSubmission) -> str:
    created = lead.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        "📩 <b>Новая заявка с сайта</b>\n"
        "━━━━━━━━━━━━━━\n"
        f"🆔 <b>ID:</b> <code>{lead.id}</code>\n"
        f"📌 <b>Статус:</b> {STATUS_LABELS[lead.status]}\n"
        f"🗂 <b>Форма:</b> {FORM_TYPE_LABELS.get(lead.form_type, lead.form_type.value)}\n"
        f"🕒 <b>Создана:</b> {created}\n\n"
        "👤 <b>Контакт</b>\n"
        f"• <b>ФИО:</b> {lead.fio}\n"
        f"• <b>Email:</b> <code>{lead.email}</code>\n"
        f"• <b>Телефон:</b> <code>{lead.phone}</code>\n"
        f"• <b>Компания:</b> {lead.company}\n\n"
        "📝 <b>Задача</b>\n"
        f"{lead.task}\n"
    )


def render_dashboard_lead_page(
    *,
    lead: LeadSubmission | None,
    status_label: str,
    total: int,
    position: int | None,
) -> str:
    if lead is None:
        return (
            f"📂 <b>{status_label}</b>\n"
            "━━━━━━━━━━━━━━\n"
            "Заявок в этом разделе нет."
        )
    return (
        f"📂 <b>{status_label}</b>\n"
        "━━━━━━━━━━━━━━\n"
        f"Позиция: <b>{position}/{total}</b>\n\n"
        f"{render_telegram_message(lead)}"
    )


def render_stats_message(stats: LeadStats) -> str:
    since_line = ""
    if stats.since is not None:
        since_line = f"\nПериод с: <code>{stats.since.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</code>"
    return (
        f"📊 <b>Статистика заявок</b>\n"
        "━━━━━━━━━━━━━━\n"
        f"<b>{stats.period_label}</b>{since_line}\n\n"
        f"Всего: <b>{stats.total}</b>\n"
        f"Не обработано: <b>{stats.not_processed}</b>\n"
        f"В работе: <b>{stats.in_progress}</b>\n"
        f"Отказы: <b>{stats.rejected}</b>\n"
    )
