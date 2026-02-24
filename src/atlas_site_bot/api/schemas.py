from pydantic import BaseModel, ConfigDict, EmailStr, Field

from atlas_site_bot.domain.enums import FormType, LeadStatus


class FormSubmissionRequest(BaseModel):
    task: str = Field(min_length=1, max_length=2000)
    form_type: FormType = FormType.MAIN_PAGE
    fio: str = Field(min_length=1, max_length=255)
    email: EmailStr
    phone: str = Field(min_length=1, max_length=50)
    company: str = Field(min_length=1, max_length=255)


class FormSubmissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: LeadStatus

