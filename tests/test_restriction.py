"""
Unit tests for the core restriction logic (pretix_email_restrictions.restriction).

These tests exercise validate_restrictions() directly and do not require
a running HTTP server or a real checkout session.
"""
from decimal import Decimal

import pytest

from pretix.base.models import Event, Order

from pretix_email_restrictions.restriction import (
    RestrictionViolated,
    get_effective_setting,
    validate_restrictions,
)

from .conftest import make_order


# ---------------------------------------------------------------------------
# get_effective_setting – hierarchy tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEffectiveSetting:
    def test_returns_none_when_nothing_set(self, event):
        assert get_effective_setting(event, "email_restriction_max_per_email", as_type=int) is None

    def test_organizer_setting_used_as_default(self, event, organizer):
        organizer.settings.set("email_restriction_max_per_email", 3)
        assert get_effective_setting(event, "email_restriction_max_per_email", as_type=int) == 3

    def test_event_overrides_organizer_when_allowed(self, event, organizer):
        organizer.settings.set("email_restriction_max_per_email", 3)
        organizer.settings.set("email_restriction_allow_event_override", True)
        event.settings.set("email_restriction_max_per_email", 10)
        assert get_effective_setting(event, "email_restriction_max_per_email", as_type=int) == 10

    def test_event_override_ignored_when_disallowed(self, event, organizer):
        organizer.settings.set("email_restriction_max_per_email", 3)
        organizer.settings.set("email_restriction_allow_event_override", False)
        event.settings.set("email_restriction_max_per_email", 10)
        assert get_effective_setting(event, "email_restriction_max_per_email", as_type=int) == 3

    def test_event_inherits_when_own_setting_is_empty(self, event, organizer):
        organizer.settings.set("email_restriction_max_per_email", 5)
        organizer.settings.set("email_restriction_allow_event_override", True)
        # event has no setting → falls back to organizer
        assert get_effective_setting(event, "email_restriction_max_per_email", as_type=int) == 5


# ---------------------------------------------------------------------------
# validate_restrictions – per-order limit
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPerOrderLimit:
    def test_passes_when_no_limit_set(self, event):
        validate_restrictions(event, "user@example.com", cart_count=100)

    def test_passes_exactly_at_limit(self, event):
        event.settings.set("email_restriction_max_per_order", 3)
        validate_restrictions(event, "user@example.com", cart_count=3)

    def test_raises_when_over_limit(self, event):
        event.settings.set("email_restriction_max_per_order", 2)
        with pytest.raises(RestrictionViolated):
            validate_restrictions(event, "user@example.com", cart_count=3)

    def test_limit_via_organizer_setting(self, event, organizer):
        organizer.settings.set("email_restriction_max_per_order", 1)
        with pytest.raises(RestrictionViolated):
            validate_restrictions(event, "user@example.com", cart_count=2)


# ---------------------------------------------------------------------------
# validate_restrictions – per-email limit
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPerEmailLimit:
    def test_passes_when_no_limit_set(self, event, item):
        make_order(event, "user@example.com", item, n_positions=50)
        validate_restrictions(event, "user@example.com", cart_count=50)

    def test_passes_with_no_existing_orders(self, event):
        event.settings.set("email_restriction_max_per_email", 3)
        validate_restrictions(event, "new@example.com", cart_count=3)

    def test_passes_exactly_at_limit(self, event, item):
        event.settings.set("email_restriction_max_per_email", 5)
        make_order(event, "user@example.com", item, n_positions=3)
        validate_restrictions(event, "user@example.com", cart_count=2)

    def test_raises_when_existing_plus_cart_exceeds_limit(self, event, item):
        event.settings.set("email_restriction_max_per_email", 3)
        make_order(event, "user@example.com", item, n_positions=2)
        with pytest.raises(RestrictionViolated):
            validate_restrictions(event, "user@example.com", cart_count=2)

    def test_email_comparison_is_case_insensitive(self, event, item):
        event.settings.set("email_restriction_max_per_email", 1)
        make_order(event, "User@Example.COM", item, n_positions=1)
        with pytest.raises(RestrictionViolated):
            validate_restrictions(event, "user@example.com", cart_count=1)

    def test_cancelled_orders_not_counted(self, event, item):
        event.settings.set("email_restriction_max_per_email", 2)
        make_order(event, "user@example.com", item, n_positions=2, status=Order.STATUS_CANCELED)
        # Cancelled order does not count → two more tickets are allowed
        validate_restrictions(event, "user@example.com", cart_count=2)

    def test_expired_orders_not_counted(self, event, item):
        event.settings.set("email_restriction_max_per_email", 2)
        make_order(event, "user@example.com", item, n_positions=2, status=Order.STATUS_EXPIRED)
        validate_restrictions(event, "user@example.com", cart_count=2)

    def test_pending_orders_are_counted(self, event, item):
        event.settings.set("email_restriction_max_per_email", 2)
        make_order(event, "user@example.com", item, n_positions=1, status=Order.STATUS_PENDING)
        with pytest.raises(RestrictionViolated):
            validate_restrictions(event, "user@example.com", cart_count=2)

    def test_paid_orders_are_counted(self, event, item):
        event.settings.set("email_restriction_max_per_email", 2)
        make_order(event, "user@example.com", item, n_positions=2, status=Order.STATUS_PAID)
        with pytest.raises(RestrictionViolated):
            validate_restrictions(event, "user@example.com", cart_count=1)

    def test_different_events_are_independent(self, organizer, event, item):
        """Tickets from another event must not count towards this event's limit."""
        from django_scopes import scopes_disabled

        with scopes_disabled():
            other_event = Event.objects.create(
                organizer=organizer,
                name="Other Event",
                slug="other",
                plugins="pretix_email_restrictions",
                date_from=event.date_from,
            )
            other_item = item.__class__.objects.create(
                event=other_event, name="Ticket", default_price=Decimal("10.00")
            )
        event.settings.set("email_restriction_max_per_email", 2)
        # 5 tickets in other event → must not matter
        make_order(other_event, "user@example.com", other_item, n_positions=5)
        validate_restrictions(event, "user@example.com", cart_count=2)

    def test_exclude_order_avoids_double_counting(self, event, item):
        """
        When called from order_placed, the new order is already in the DB.
        Passing exclude_order must prevent it from being counted twice.
        """
        event.settings.set("email_restriction_max_per_email", 2)
        order = make_order(event, "user@example.com", item, n_positions=2)
        # Without exclude: 2 existing + 2 new = 4 → would raise
        # With exclude: 0 existing + 2 new = 2 → passes
        validate_restrictions(event, "user@example.com", cart_count=2, exclude_order=order)

    def test_empty_email_skips_per_email_check(self, event, item):
        event.settings.set("email_restriction_max_per_email", 1)
        make_order(event, "user@example.com", item, n_positions=1)
        # Empty email → per-email check is skipped entirely
        validate_restrictions(event, "", cart_count=10)


# ---------------------------------------------------------------------------
# Both limits active simultaneously
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestBothLimits:
    def test_per_order_checked_before_per_email(self, event):
        event.settings.set("email_restriction_max_per_order", 1)
        event.settings.set("email_restriction_max_per_email", 100)
        with pytest.raises(RestrictionViolated):
            validate_restrictions(event, "user@example.com", cart_count=2)

    def test_per_email_checked_when_per_order_passes(self, event, item):
        event.settings.set("email_restriction_max_per_order", 5)
        event.settings.set("email_restriction_max_per_email", 3)
        make_order(event, "user@example.com", item, n_positions=2)
        with pytest.raises(RestrictionViolated):
            validate_restrictions(event, "user@example.com", cart_count=2)


# ---------------------------------------------------------------------------
# Custom error message
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestErrorMessage:
    def test_default_message_is_returned(self, event):
        event.settings.set("email_restriction_max_per_order", 1)
        with pytest.raises(RestrictionViolated) as exc_info:
            validate_restrictions(event, "user@example.com", cart_count=2)
        assert len(str(exc_info.value)) > 0

    def test_custom_message_is_used(self, event):
        event.settings.set("email_restriction_max_per_order", 1)
        event.settings.set("email_restriction_error_message", "Custom error!")
        with pytest.raises(RestrictionViolated) as exc_info:
            validate_restrictions(event, "user@example.com", cart_count=2)
        assert "Custom error!" in str(exc_info.value)

    def test_organizer_message_inherited_by_event(self, event, organizer):
        organizer.settings.set("email_restriction_max_per_order", 1)
        organizer.settings.set("email_restriction_error_message", "Organizer says no.")
        with pytest.raises(RestrictionViolated) as exc_info:
            validate_restrictions(event, "user@example.com", cart_count=2)
        assert "Organizer says no." in str(exc_info.value)
