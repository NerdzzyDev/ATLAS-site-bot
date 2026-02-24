from enum import Enum


class FormType(str, Enum):
    MAIN_PAGE = "main_page"


class LeadStatus(str, Enum):
    NOT_PROCESSED = "not_processed"
    IN_PROGRESS = "in_progress"
    REJECTED = "rejected"


class LeadAction(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"

