"""
Tests for the order_placed signal handler (API / direct order creation path).
"""
import pytest

from pretix.base.models import Order
from pretix.base.services.orders import OrderError

from pretix_email_restrictions.signals import validate_order_on_placement

from .conftest import make_order


def _call_signal(event, order):
    """Directly invoke the signal handler (bypasses Django signal dispatch)."""
    validate_order_on_placement(sender=event, order=order)


@pytest.mark.django_db
class TestOrderPlacedSignal:
    def test_no_restriction_configured_passes(self, event, item):
        order = make_order(event, "user@example.com", item, n_positions=3)
        _call_signal(event, order)  # no limits → must not raise

    def test_passes_when_under_order_email_limit(self, event, item):
        """First order with this email → 0 existing < 5 → passes."""
        event.settings.set("email_restriction_max_per_email", 5)
        order = make_order(event, "user@example.com", item, n_positions=3)
        _call_signal(event, order)

    def test_raises_order_error_when_at_order_email_limit(self, event, item):
        """Two existing orders with limit=2 → a third one is blocked."""
        event.settings.set("email_restriction_max_per_email", 2)
        make_order(event, "user@example.com", item)  # 1st order
        make_order(event, "user@example.com", item)  # 2nd order → at limit
        new_order = make_order(event, "user@example.com", item)
        with pytest.raises(OrderError):
            _call_signal(event, new_order)  # 2 existing (excl. new) >= 2 → blocked

    def test_does_not_double_count_new_order(self, event, item):
        """
        The new order is already persisted when the signal fires.
        It must be excluded from the existing-order count.
        """
        event.settings.set("email_restriction_max_per_email", 1)
        order = make_order(event, "user@example.com", item)
        # 1 order in DB (itself), but excluded → 0 existing < 1 → passes
        _call_signal(event, order)

    def test_raises_order_error_when_over_attendee_email_limit(self, event, item):
        """Attendee email already on 1 ticket, limit=1 → new position blocked."""
        event.settings.set("email_restriction_max_per_attendee_email", 1)
        make_order(event, "other@example.com", item, attendee_email="attendee@test.com")
        new_order = make_order(event, "user@example.com", item, attendee_email="attendee@test.com")
        with pytest.raises(OrderError):
            _call_signal(event, new_order)  # 1 existing + 1 new > 1 → blocked

    def test_cancelled_orders_excluded_from_count(self, event, item):
        event.settings.set("email_restriction_max_per_email", 1)
        make_order(event, "user@example.com", item, status=Order.STATUS_CANCELED)
        new_order = make_order(event, "user@example.com", item)
        # Cancelled order does not count → 0 active (excl. new) < 1 → passes
        _call_signal(event, new_order)

    def test_organizer_limit_enforced(self, event, organizer, item):
        organizer.settings.set("email_restriction_max_per_email", 1)
        make_order(event, "user@example.com", item)  # 1st order at limit
        new_order = make_order(event, "user@example.com", item)
        with pytest.raises(OrderError):
            _call_signal(event, new_order)  # 1 existing (excl. new) >= 1 → blocked

    def test_event_override_takes_precedence(self, event, organizer, item):
        organizer.settings.set("email_restriction_max_per_email", 1)
        organizer.settings.set("email_restriction_allow_event_override", True)
        event.settings.set("email_restriction_max_per_email", 5)
        order = make_order(event, "user@example.com", item)
        _call_signal(event, order)  # 0 existing (excl. self) < 5 → passes

    def test_no_email_skips_per_email_check(self, event, item):
        event.settings.set("email_restriction_max_per_email", 1)
        order = make_order(event, "", item, n_positions=5)
        _call_signal(event, order)  # empty email → skip per-email check
