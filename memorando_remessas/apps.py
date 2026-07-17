from django.apps import AppConfig


class MemorandoRemessasConfig(AppConfig):
    default_auto_field = (
        "django.db.models.BigAutoField"
    )

    name = "memorando_remessas"
    verbose_name = "Memorandos de Remessa"

    def ready(self):
        import memorando_remessas.signals  # noqa: F401