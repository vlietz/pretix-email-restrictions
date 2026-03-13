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
  - Max tickets per order email:    2
  - Max tickets per attendee email: 2
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
            Voucher,
        )

        with scopes_disabled():
            self._run(
                User, Organizer, SalesChannel, Team, Event, Item, Quota, Voucher
            )

    def _run(self, User, Organizer, SalesChannel, Team, Event, Item, Quota, Voucher):
        # ------------------------------------------------------------------
        # Superuser
        # ------------------------------------------------------------------
        try:
            user = User.objects.get(email=ADMIN_EMAIL)
            created = False
        except User.DoesNotExist:
            user = User.objects.create_superuser(ADMIN_EMAIL, ADMIN_PASSWORD)
            created = True

        if created:
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

        # banktransfer is a hybrid event+organizer plugin and must be enabled
        # at the organizer level as well, otherwise the payment provider signal
        # is filtered out and the payment step shows "no providers enabled".
        org_plugins = set(p for p in organizer.plugins.split(",") if p)
        org_plugins.add("pretix.plugins.banktransfer")
        organizer.plugins = ",".join(sorted(org_plugins))
        organizer.save()

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
            defaults={"default_price": Decimal("10.00"), "admission": True},
        )
        # Ensure admission is set even on existing items
        if not item.admission:
            item.admission = True
            item.save()

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
        event.settings.set("email_restriction_max_per_attendee_email", 2)
        event.settings.set(
            "email_restriction_error_message",
            "Sorry, a maximum of 2 tickets per email address is allowed for this event.",
        )
        # Allow event-level overrides at organizer level (default)
        organizer.settings.set("email_restriction_allow_event_override", True)

        # Ask for (and require) individual attendee details per ticket:
        # first name + last name + email address (mirrors typical prod setup).
        event.settings.set("attendee_names_asked", True)
        event.settings.set("attendee_names_required", True)
        event.settings.set("name_scheme", "given_family")  # separate first / last fields
        event.settings.set("attendee_emails_asked", True)
        event.settings.set("attendee_emails_required", True)

        # ------------------------------------------------------------------
        # Payment providers
        # ------------------------------------------------------------------
        # Enable bank transfer (for paid orders) and the free-order provider
        # (for €0 orders, e.g. when a 100 % voucher is applied).
        event.settings.set("payment_banktransfer__enabled", True)
        event.settings.set("payment_free__enabled", True)

        # ------------------------------------------------------------------
        # Free vouchers for testing (price_mode=set, value=0)
        # ------------------------------------------------------------------
        for code in ("FREE1", "FREE2", "FREE3", "FREE4", "FREE5"):
            Voucher.objects.get_or_create(
                event=event,
                code=code,
                defaults={
                    "max_usages": 1,
                    "redeemed": 0,
                    "price_mode": "set",
                    "value": Decimal("0.00"),
                    "item": item,
                },
            )
        self.stdout.write("  Created/verified free vouchers: FREE1 … FREE5")

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
        self.stdout.write("    Max tickets per order email:    2")
        self.stdout.write("    Max tickets per attendee email: 2")
        self.stdout.write("")
        self.stdout.write("  Free vouchers (set price to €0, single-use each)")
        self.stdout.write("    FREE1  FREE2  FREE3  FREE4  FREE5")
        self.stdout.write("    Use one per checkout at the voucher/discount step.")
        self.stdout.write("")
        self.stdout.write("  Test scenarios")
        self.stdout.write("    1. Add 1 ticket + voucher FREE1 → check out → should succeed")
        self.stdout.write("    2. Add 1 ticket + voucher FREE2, same email → should succeed (total = 2 = limit)")
        self.stdout.write("    3. Add 1 ticket + voucher FREE3, same email → should be blocked (total = 3 > 2)")
        self.stdout.write("    4. Click 'Change email address' → enter different email → should succeed")
        self.stdout.write("    5. Change limit:  Settings → Email Restrictions")
        self.stdout.write("")
