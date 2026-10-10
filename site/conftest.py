import pytest


@pytest.fixture(autouse=True)
def _plain_static_storage(settings):
    """В тестах статика без манифеста: не нужен collectstatic перед прогоном."""
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
