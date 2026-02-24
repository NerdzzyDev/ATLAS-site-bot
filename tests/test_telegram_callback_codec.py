from uuid import uuid4

from atlas_site_bot.adapters.telegram_bot import _callback_data, _parse_callback_data
from atlas_site_bot.domain.enums import LeadAction


def test_callback_data_roundtrip() -> None:
    lead_id = uuid4()

    data = _callback_data(LeadAction.ACCEPT, lead_id)
    action, parsed_id = _parse_callback_data(data)

    assert action == LeadAction.ACCEPT
    assert parsed_id == lead_id
