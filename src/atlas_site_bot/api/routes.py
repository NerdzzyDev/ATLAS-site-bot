from fastapi import APIRouter, HTTPException, status

from atlas_site_bot.api.schemas import FormSubmissionRequest, FormSubmissionResponse
from atlas_site_bot.application.use_cases import SubmitLeadCommand


def build_router(container) -> APIRouter:  # noqa: ANN001
    router = APIRouter(prefix="/api/v1", tags=["forms"])

    @router.post(
        "/forms",
        response_model=FormSubmissionResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def submit_form(payload: FormSubmissionRequest) -> FormSubmissionResponse:
        try:
            lead = await container.submit_lead_service.submit(
                SubmitLeadCommand(
                    task=payload.task,
                    form_type=payload.form_type,
                    fio=payload.fio,
                    email=payload.email,
                    phone=payload.phone,
                    company=payload.company,
                )
            )
        except Exception as exc:
            if hasattr(container, "telegram_notifier"):
                await container.telegram_notifier.send_error_alert(
                    "Ошибка обработки формы на API. Заявка не была доставлена в Telegram."
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to process form",
            ) from exc

        return FormSubmissionResponse(id=str(lead.id), status=lead.status)

    return router
