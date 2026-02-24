from fastapi.testclient import TestClient

from atlas_site_bot.container import ApplicationContainer
from atlas_site_bot.main import create_app
from atlas_site_bot.settings import Settings


def test_submit_form_endpoint() -> None:
    settings = Settings(telegram_enabled=False, database_url="")
    app = create_app(settings=settings, container=ApplicationContainer(settings))

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/forms",
            json={
                "task": "Нужен расчет проекта",
                "form_type": "main_page",
                "fio": "Анна Смирнова",
                "email": "anna@example.com",
                "phone": "+71234567890",
                "company": "Atlas LLC",
            },
        )

    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["status"] == "not_processed"


def test_submit_form_validation_error() -> None:
    settings = Settings(telegram_enabled=False, database_url="")
    app = create_app(settings=settings, container=ApplicationContainer(settings))

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/forms",
            json={
                "task": "",
                "form_type": "main_page",
                "fio": "",
                "email": "bad",
                "phone": "",
                "company": "",
            },
        )

    assert response.status_code == 422
