from django.urls import path

from . import views

# These patterns are registered under the namespace "plugins:pretix_email_restrictions"
# by pretix's plugin URL loader.

urlpatterns = [
    # Event-level settings
    path(
        "control/event/<str:organizer>/<str:event>/email-restrictions/",
        views.EventEmailRestrictionSettingsView.as_view(),
        name="settings",
    ),
    # Organizer-level settings
    path(
        "control/organizer/<str:organizer>/email-restrictions/",
        views.OrganizerEmailRestrictionSettingsView.as_view(),
        name="organizer.settings",
    ),
]
