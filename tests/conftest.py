"""
Shared pytest fixtures for the pretix-email-restrictions test suite.
"""
import datetime
import uuid
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django_scopes import scopes_disabled

from pretix.base.models import (
    Event,
    Item,
    Order,
    OrderPosition,
    Organizer,
    Quota,
    SalesChannel,
    Team,
    User,
)

UTC = ZoneInfo("UTC")


# ---------------------------------------------------------------------------
# Core pretix objects
# ---------------------------------------------------------------------------


@pytest.fixture
def organizer(db):
    org = Organizer.objects.create(name="Test Organizer", slug="testorg")
    # Every organizer needs a web sales channel for orders to be created.
    with scopes_disabled():
        SalesChannel.objects.get_or_create(
            organizer=org,
            identifier="web",
            defaults={"label": "Web shop", "type": "web"},
        )
    return org


@pytest.fixture
def event(organizer):
    with scopes_disabled():
        event = Event.objects.create(
            organizer=organizer,
            name="Test Event",
            slug="test",
            plugins="pretix_email_restrictions",
            date_from=datetime.datetime(2030, 6, 1, 10, 0, 0, tzinfo=UTC),
            presale_start=datetime.datetime(2020, 1, 1, tzinfo=UTC),
            presale_end=datetime.datetime(2030, 5, 31, tzinfo=UTC),
            live=True,
        )
    return event


@pytest.fixture
def item(event):
    with scopes_disabled():
        quota = Quota.objects.create(event=event, name="Main", size=100)
        item = Item.objects.create(event=event, name="Ticket", default_price=Decimal("10.00"))
        quota.items.add(item)
    return item


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser("admin@example.com", "admin")


@pytest.fixture
def admin_team(organizer, admin_user):
    with scopes_disabled():
        team = Team.objects.create(
            organizer=organizer,
            name="Admin",
            all_events=True,
            can_change_event_settings=True,
            can_change_organizer_settings=True,
            can_view_orders=True,
            can_change_orders=True,
        )
        team.members.add(admin_user)
    return team


# ---------------------------------------------------------------------------
# Helpers to create orders / positions
# ---------------------------------------------------------------------------


def make_order(event, email, item, n_positions=1, status=Order.STATUS_PAID):
    """Create an order with *n_positions* positions."""
    with scopes_disabled():
        sales_channel = SalesChannel.objects.get(organizer=event.organizer, identifier="web")
        order = Order.objects.create(
            code=f"T{uuid.uuid4().hex[:7].upper()}",
            event=event,
            email=email,
            status=status,
            datetime=datetime.datetime.now(UTC),
            expires=datetime.datetime(2030, 12, 31, tzinfo=UTC),
            total=item.default_price * n_positions,
            locale="en",
            sales_channel=sales_channel,
        )
        for _ in range(n_positions):
            OrderPosition.objects.create(
                order=order,
                item=item,
                price=item.default_price,
            )
    return order


@pytest.fixture
def make_order_fixture(event, item):
    """Return a factory callable pre-bound to the event and item."""

    def _factory(email, n_positions=1, status=Order.STATUS_PAID):
        return make_order(event, email, item, n_positions=n_positions, status=status)

    return _factory
