from django.utils.translation import gettext_lazy as _

try:
    from pretix.base.plugins import PluginConfig  # noqa – verifies pretix version
except ImportError:
    raise RuntimeError("Please use pretix 2026.1.0 or later to run this plugin.")


class PretixPluginMeta:
    name = _("Email Restrictions")
    author = "Community"
    version = "1.0.0"
    visible = True
    description = _("Limit the number of tickets that can be ordered per email address per event.")
    category = "FEATURE"
    compatibility = "pretix>=2026.1.0"


default_app_config = "pretix_email_restrictions.apps.PluginApp"
