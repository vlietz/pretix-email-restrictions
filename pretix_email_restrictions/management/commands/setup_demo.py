"""
Management command: setup_demo

Creates a complete demo environment so you can immediately test the
email-restriction plugin manually in a running pretix instance.

Usage (inside the Docker container):
    pretix setup_demo

What it creates
---------------
- Superuser          admin@example.com / admin1234
- Organizer          "Demo Organizer"  (slug: demo)
- Web sales channel  for the organizer
- Admin team         with full permissions, superuser as member
- Event              "Email Restriction Test Event"  (slug: restrict-test)
  - Plugin enabled:  pretix_email_restrictions
  - Payment method:  bank transfer (built-in, no API keys needed)
  - Ticket item:     "Standard Ticket"  €10.00
  - Quota:           100 tickets
  - Live:            yes (shop is open)
- Email restrictions configured on the event:
  - Max tickets per email:  2
  - Max tickets per order:  3
  - Custom error message set

The command is idempotent — running it twice is safe.
"""

import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand

UTC = ZoneInfo("UTC")

ORGANIZER_SLUG = "demo"
EVENT_SLUG = "restrict-test"
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin1234"  # noqa: S105 – demo only


class Command(BaseCommand):
    help = "Bootstrap a demo organizer and event for manual plugin testing."

    def handle(self, *args, **options):
        from django_scopes import scopes_disabled

        from pretix.base.models import (
            Event,
            Item,
            Organizer,
            Quota,
            SalesChannel,
            Team,
            User,
        )

        with scopes_disabled():
            self._run(
                User, Organizer, SalesChannel, Team, Event, Item, Quota
            )

    def _run(self, User, Organizer, SalesChannel, Team, Event, Item, Quota):
        # ------------------------------------------------------------------
        # Superuser
        # ------------------------------------------------------------------
        user, created = User.objects.get_or_create(
            email=ADMIN_EMAIL,
            defaults={"is_staff": True, "is_superuser": True},
        )
        if created:
            user.set_password(ADMIN_PASSWORD)
            user.save()
            self.stdout.write(f"  Created superuser {ADMIN_EMAIL}")
        else:
            self.stdout.write(f"  Superuser {ADMIN_EMAIL} already exists")

        # ------------------------------------------------------------------
        # Organizer
        # ------------------------------------------------------------------
        organizer, created = Organizer.objects.get_or_create(
            slug=ORGANIZER_SLUG,
            defaults={"name": "Demo Organizer"},
        )
        if created:
            self.stdout.write(f"  Created organizer '{organizer.name}'")
        else:
            self.stdout.write(f"  Organizer '{organizer.name}' already exists")

        # ------------------------------------------------------------------
        # Web sales channel (required for orders in pretix 2026.x)
        # ------------------------------------------------------------------
        SalesChannel.objects.get_or_create(
            organizer=organizer,
            identifier="web",
            defaults={"label": "Web shop", "type": "web"},
        )

        # ------------------------------------------------------------------
        # Admin team
        # ------------------------------------------------------------------
        team, _ = Team.objects.get_or_create(
            organizer=organizer,
            name="Admins",
            defaults={
                "all_events": True,
                "can_change_event_settings": True,
                "can_change_organizer_settings": True,
                "can_view_orders": True,
                "can_change_orders": True,
                "can_create_events": True,
            },
        )
        team.members.add(user)

        # ------------------------------------------------------------------
        # Event
        # ------------------------------------------------------------------
        now = datetime.datetime.now(UTC)
        event, created = Event.objects.get_or_create(
            organizer=organizer,
            slug=EVENT_SLUG,
            defaults={
                "name": "Email Restriction Test Event",
                "currency": "EUR",
                # Plugin list: bank transfer for payments + our plugin
                "plugins": "pretix.plugins.banktransfer,pretix_email_restrictions",
                "date_from": now + datetime.timedelta(days=30),
                "presale_start": now - datetime.timedelta(days=1),
                "presale_end": now + datetime.timedelta(days=29),
                "live": True,
            },
        )
        if created:
            self.stdout.write(f"  Created event '{event.name}'")
        else:
            self.stdout.write(f"  Event '{event.name}' already exists")
            # Ensure the plugin is in the plugins list even for existing events
            plugins = set(p for p in event.plugins.split(",") if p)
            plugins.add("pretix_email_restrictions")
            event.plugins = ",".join(sorted(plugins))
            event.live = True
            event.save()

        # ------------------------------------------------------------------
        # Ticket item + quota
        # ------------------------------------------------------------------
        item, _ = Item.objects.get_or_create(
            event=event,
            name="Standard Ticket",
            defaults={"default_price": Decimal("10.00")},
        )

        quota, _ = Quota.objects.get_or_create(
            event=event,
            name="Main quota",
            defaults={"size": 100},
        )
        quota.items.add(item)

        # ------------------------------------------------------------------
        # Email restriction settings on the event
        # ------------------------------------------------------------------
        event.settings.set("email_restriction_max_per_email", 2)
        event.settings.set("email_restriction_max_per_order", 3)
        event.settings.set(
            "email_restriction_error_message",
            "Sorry, a maximum of 2 tickets per email address is allowed for this event.",
        )
        # Allow event-level overrides at organizer level (default)
        organizer.settings.set("email_restriction_allow_event_override", True)

        # ------------------------------------------------------------------
        # Summary
        # ------------------------------------------------------------------
        base = "http://localhost:8345"
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("  Demo environment ready"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write("")
        self.stdout.write("  Admin login")
        self.stdout.write(f"    URL:       {base}/control/")
        self.stdout.write(f"    Email:     {ADMIN_EMAIL}")
        self.stdout.write(f"    Password:  {ADMIN_PASSWORD}")
        self.stdout.write("")
        self.stdout.write("  Shop (public checkout)")
        self.stdout.write(f"    URL:       {base}/{ORGANIZER_SLUG}/{EVENT_SLUG}/")
        self.stdout.write("")
        self.stdout.write("  Email restriction settings")
        self.stdout.write("    Max tickets per email:  2")
        self.stdout.write("    Max tickets per order:  3")
        self.stdout.write("")
        self.stdout.write("  Test scenarios")
        self.stdout.write("    1. Add 1 ticket → check out → should succeed")
        self.stdout.write("    2. Add 2 tickets, same email → should be blocked")
        self.stdout.write("    3. Add 4 tickets in one order → blocked by per-order limit")
        self.stdout.write("    4. Change limits:  Settings → Email Restrictions")
        self.stdout.write("")
