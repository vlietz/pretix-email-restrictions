from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PluginApp(AppConfig):
    name = "pretix_email_restrictions"
    verbose_name = "pretix Email Restrictions"

    class PretixPluginMeta:
        name = _("Email Restrictions")
        author = "Community"
        version = "1.0.0"
        visible = True
        description = _("Limit the number of tickets that can be ordered per email address per event.")
        category = "FEATURE"
        compatibility = "pretix>=2026.1.0"

    def ready(self):
        from . import signals  # noqa – registers all @receiver decorators
