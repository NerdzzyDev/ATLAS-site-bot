from atlas_site_bot.domain.enums import LeadAction, LeadStatus
from atlas_site_bot.domain.exceptions import InvalidLeadTransitionError


def available_actions_for_status(status: LeadStatus) -> list[LeadAction]:
    if status == LeadStatus.NOT_PROCESSED:
        return [LeadAction.ACCEPT, LeadAction.REJECT]
    if status == LeadStatus.IN_PROGRESS:
        return [LeadAction.REJECT]
    return []


def transition_status(current: LeadStatus, action: LeadAction) -> LeadStatus:
    if action == LeadAction.ACCEPT and current == LeadStatus.NOT_PROCESSED:
        return LeadStatus.IN_PROGRESS
    if action == LeadAction.REJECT and current in {
        LeadStatus.NOT_PROCESSED,
        LeadStatus.IN_PROGRESS,
    }:
        return LeadStatus.REJECTED
    raise InvalidLeadTransitionError(
        f"Action '{action.value}' is not allowed from status '{current.value}'"
    )

