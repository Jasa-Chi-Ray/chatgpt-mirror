from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "app.accounts"

    def ready(self):
        from . import revocations  # noqa: F401
