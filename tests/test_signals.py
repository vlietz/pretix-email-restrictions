"""
Tests for the order_placed signal handler (API / direct order creation path).
"""
import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from pretix.base.models import Order, OrderPosition
from pretix.base.services.orders import OrderError

from pretix_email_restrictions.signals import validate_order_on_placement

from .conftest import make_order

UTC = ZoneInfo("UTC")


def _call_signal(event, order):
    """Directly invoke the signal handler (bypasses Django signal dispatch)."""
    validate_order_on_placement(sender=event, order=order)


@pytest.mark.django_db
class TestOrderPlacedSignal:
    def test_no_restriction_configured_passes(self, event, item):
        order = make_order(event, "user@example.com", item, n_positions=3)
        # Must not raise
        _call_signal(event, order)

    def test_passes_when_under_per_email_limit(self, event, item):
        event.settings.set("email_restriction_max_per_email", 5)
        order = make_order(event, "user@example.com", item, n_positions=3)
        _call_signal(event, order)  # 3 ≤ 5 → OK

    def test_raises_order_error_when_over_per_email_limit(self, event, item):
        event.settings.set("email_restriction_max_per_email", 3)
        # Existing paid order: 2 tickets
        make_order(event, "user@example.com", item, n_positions=2)
        # New order: 2 tickets → 2 + 2 = 4 > 3
        new_order = make_order(event, "user@example.com", item, n_positions=2)
        with pytest.raises(OrderError):
            _call_signal(event, new_order)

    def test_does_not_double_count_new_order(self, event, item):
        """
        The new order is already persisted when the signal fires.
        It must be excluded from the "existing tickets" count.
        """
        event.settings.set("email_restriction_max_per_email", 3)
        order = make_order(event, "user@example.com", item, n_positions=3)
        # 3 positions in the new order, limit is 3 → exactly at limit → must pass
        _call_signal(event, order)

    def test_raises_order_error_when_over_per_order_limit(self, event, item):
        event.settings.set("email_restriction_max_per_order", 2)
        order = make_order(event, "user@example.com", item, n_positions=3)
        with pytest.raises(OrderError):
            _call_signal(event, order)

    def test_cancelled_orders_excluded_from_count(self, event, item):
        event.settings.set("email_restriction_max_per_email", 2)
        make_order(event, "user@example.com", item, n_positions=2, status=Order.STATUS_CANCELED)
        new_order = make_order(event, "user@example.com", item, n_positions=2)
        # Cancelled order does not count → 0 + 2 = 2 ≤ 2 → OK
        _call_signal(event, new_order)

    def test_organizer_limit_enforced(self, event, organizer, item):
        organizer.settings.set("email_restriction_max_per_email", 1)
        order = make_order(event, "user@example.com", item, n_positions=2)
        with pytest.raises(OrderError):
            _call_signal(event, order)

    def test_event_override_takes_precedence(self, event, organizer, item):
        organizer.settings.set("email_restriction_max_per_email", 1)
        organizer.settings.set("email_restriction_allow_event_override", True)
        event.settings.set("email_restriction_max_per_email", 5)
        order = make_order(event, "user@example.com", item, n_positions=3)
        _call_signal(event, order)  # 3 ≤ 5 → OK

    def test_no_email_skips_per_email_check(self, event, item):
        event.settings.set("email_restriction_max_per_email", 1)
        order = make_order(event, "", item, n_positions=5)
        _call_signal(event, order)  # empty email → skip per-email check
