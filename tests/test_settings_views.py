"""
Tests for the admin settings views (event-level and organizer-level).
"""
import pytest
from django.test import Client
from django.urls import reverse
from django_scopes import scopes_disabled

from pretix.base.models import Event, Organizer


def fresh_event(event):
    """Return a new Event instance from the DB, bypassing any in-memory cache."""
    with scopes_disabled():
        return Event.objects.get(pk=event.pk)


def fresh_organizer(organizer):
    with scopes_disabled():
        return Organizer.objects.get(pk=organizer.pk)


@pytest.fixture
def client(admin_user, admin_team):  # admin_team ensures permissions
    c = Client()
    c.force_login(admin_user)
    return c


# ---------------------------------------------------------------------------
# Event settings view
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestEventSettingsView:
    def _url(self, event):
        return reverse(
            "plugins:pretix_email_restrictions:settings",
            kwargs={"organizer": event.organizer.slug, "event": event.slug},
        )

    def test_get_renders(self, client, event):
        response = client.get(self._url(event))
        assert response.status_code == 200

    def test_post_saves_settings(self, client, event):
        url = self._url(event)
        response = client.post(
            url,
            {
                "email_restriction-email_restriction_max_per_email": "4",
                "email_restriction-email_restriction_max_per_order": "2",
                "email_restriction-email_restriction_error_message": "Too many tickets!",
            },
        )
        assert response.status_code in (200, 302)
        e = fresh_event(event)
        assert e.settings.get("email_restriction_max_per_email", as_type=int) == 4
        assert e.settings.get("email_restriction_max_per_order", as_type=int) == 2
        assert e.settings.get("email_restriction_error_message") == "Too many tickets!"

    def test_post_blocked_when_override_disallowed(self, client, event):
        event.organizer.settings.set("email_restriction_allow_event_override", False)
        url = self._url(event)
        response = client.post(
            url,
            {"email_restriction-email_restriction_max_per_email": "99"},
        )
        # Redirect back with warning; setting must NOT be saved
        assert response.status_code in (200, 302)
        assert fresh_event(event).settings.get("email_restriction_max_per_email", as_type=int) is None

    def test_clear_settings_by_empty_post(self, client, event):
        event.settings.set("email_restriction_max_per_email", 5)
        url = self._url(event)
        client.post(
            url,
            {
                "email_restriction-email_restriction_max_per_email": "",
                "email_restriction-email_restriction_max_per_order": "",
            },
        )
        assert fresh_event(event).settings.get("email_restriction_max_per_email", as_type=int) is None


# ---------------------------------------------------------------------------
# Organizer settings view
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestOrganizerSettingsView:
    def _url(self, organizer):
        return reverse(
            "plugins:pretix_email_restrictions:organizer.settings",
            kwargs={"organizer": organizer.slug},
        )

    def test_get_renders(self, client, organizer):
        response = client.get(self._url(organizer))
        assert response.status_code == 200

    def test_post_saves_organizer_settings(self, client, organizer):
        url = self._url(organizer)
        response = client.post(
            url,
            {
                "email_restriction-email_restriction_max_per_email": "5",
                "email_restriction-email_restriction_max_per_order": "3",
                "email_restriction-email_restriction_allow_event_override": "on",
                "email_restriction-email_restriction_error_message": "Org limit reached",
            },
        )
        assert response.status_code in (200, 302)
        o = fresh_organizer(organizer)
        assert o.settings.get("email_restriction_max_per_email", as_type=int) == 5
        assert o.settings.get("email_restriction_max_per_order", as_type=int) == 3
        assert o.settings.get("email_restriction_allow_event_override", as_type=bool) is True
        assert o.settings.get("email_restriction_error_message") == "Org limit reached"
