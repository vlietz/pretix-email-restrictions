"""
Unit tests for the core restriction logic (pretix_email_restrictions.restriction).

These tests exercise validate_restrictions() directly and do not require
a running HTTP server or a real checkout session.

Semantics tested here:
  email_restriction_max_per_email        – max *orders* per order email
  email_restriction_max_per_attendee_email – max *tickets* per attendee email
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
# validate_restrictions – order-email limit
# (counts how many *orders* have been placed with a given order email)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPerEmailLimit:
    def test_passes_when_no_limit_set(self, event, item):
        make_order(event, "user@example.com", item)
        make_order(event, "user@example.com", item)
        make_order(event, "user@example.com", item)
        # No limit configured → always passes regardless of order count
        validate_restrictions(event, "user@example.com")

    def test_passes_with_fresh_email(self, event):
        event.settings.set("email_restriction_max_per_email", 2)
        # Email never used before → 0 orders < 2 → passes regardless of cart size
        validate_restrictions(event, "new@example.com")

    def test_passes_when_under_limit(self, event, item):
        event.settings.set("email_restriction_max_per_email", 3)
        make_order(event, "user@example.com", item)
        make_order(event, "user@example.com", item)
        # 2 existing orders < 3 limit → passes
        validate_restrictions(event, "user@example.com")

    def test_raises_when_at_limit(self, event, item):
        event.settings.set("email_restriction_max_per_email", 2)
        make_order(event, "user@example.com", item)
        make_order(event, "user@example.com", item)
        # 2 existing orders >= 2 limit → blocked
        with pytest.raises(RestrictionViolated):
            validate_restrictions(event, "user@example.com")

    def test_email_comparison_is_case_insensitive(self, event, item):
        event.settings.set("email_restriction_max_per_email", 1)
        make_order(event, "User@Example.COM", item)
        with pytest.raises(RestrictionViolated):
            validate_restrictions(event, "user@example.com")

    def test_cancelled_orders_not_counted(self, event, item):
        event.settings.set("email_restriction_max_per_email", 1)
        make_order(event, "user@example.com", item, status=Order.STATUS_CANCELED)
        # Cancelled order does not count → 0 active orders < 1 → passes
        validate_restrictions(event, "user@example.com")

    def test_expired_orders_not_counted(self, event, item):
        event.settings.set("email_restriction_max_per_email", 1)
        make_order(event, "user@example.com", item, status=Order.STATUS_EXPIRED)
        validate_restrictions(event, "user@example.com")

    def test_pending_orders_are_counted(self, event, item):
        event.settings.set("email_restriction_max_per_email", 1)
        make_order(event, "user@example.com", item, status=Order.STATUS_PENDING)
        with pytest.raises(RestrictionViolated):
            validate_restrictions(event, "user@example.com")

    def test_paid_orders_are_counted(self, event, item):
        event.settings.set("email_restriction_max_per_email", 1)
        make_order(event, "user@example.com", item, status=Order.STATUS_PAID)
        with pytest.raises(RestrictionViolated):
            validate_restrictions(event, "user@example.com")

    def test_different_events_are_independent(self, organizer, event, item):
        """Orders from another event must not count towards this event's limit."""
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
        event.settings.set("email_restriction_max_per_email", 1)
        # 5 orders on the other event — must not matter
        for _ in range(5):
            make_order(other_event, "user@example.com", other_item)
        validate_restrictions(event, "user@example.com")

    def test_exclude_order_avoids_double_counting(self, event, item):
        """
        When called from order_placed the new order is already in the DB.
        exclude_order must prevent it from being counted as an existing order.
        """
        event.settings.set("email_restriction_max_per_email", 1)
        order = make_order(event, "user@example.com", item)
        # Without exclude: 1 existing >= 1 → raises
        with pytest.raises(RestrictionViolated):
            validate_restrictions(event, "user@example.com")
        # With exclude (signal scenario): 0 existing < 1 → passes
        validate_restrictions(event, "user@example.com", exclude_order=order)

    def test_empty_email_skips_per_email_check(self, event, item):
        event.settings.set("email_restriction_max_per_email", 1)
        make_order(event, "user@example.com", item)
        # Empty order email → per-email check is skipped entirely
        validate_restrictions(event, "")

    def test_limit_via_organizer_setting(self, event, organizer, item):
        organizer.settings.set("email_restriction_max_per_email", 1)
        make_order(event, "user@example.com", item)
        with pytest.raises(RestrictionViolated):
            validate_restrictions(event, "user@example.com")


# ---------------------------------------------------------------------------
# validate_restrictions – attendee-email limit
# (counts how many *tickets* carry a given attendee email across all orders)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPerAttendeeEmailLimit:
    def test_passes_when_no_limit_set(self, event, item):
        make_order(event, "x@x.com", item, n_positions=50, attendee_email="a@a.com")
        # No attendee limit → passes regardless
        validate_restrictions(event, "x@x.com", attendee_emails=["a@a.com"] * 50)

    def test_passes_with_fresh_attendee_email(self, event):
        event.settings.set("email_restriction_max_per_attendee_email", 2)
        # Email never used as attendee email → 0 + 1 ≤ 2 → passes
        validate_restrictions(event, "", attendee_emails=["new@test.com"])

    def test_passes_exactly_at_limit(self, event, item):
        event.settings.set("email_restriction_max_per_attendee_email", 2)
        make_order(event, "x@x.com", item, attendee_email="attendee@test.com")  # 1 existing
        # 1 existing + 1 in cart = 2 ≤ 2 → passes
        validate_restrictions(event, "", attendee_emails=["attendee@test.com"])

    def test_raises_when_over_limit(self, event, item):
        event.settings.set("email_restriction_max_per_attendee_email", 2)
        make_order(event, "x@x.com", item, n_positions=2, attendee_email="attendee@test.com")
        # 2 existing + 1 in cart = 3 > 2 → blocked
        with pytest.raises(RestrictionViolated):
            validate_restrictions(event, "", attendee_emails=["attendee@test.com"])

    def test_multiple_same_email_in_cart_counted(self, event):
        event.settings.set("email_restriction_max_per_attendee_email", 2)
        # 0 existing, but 3 tickets in cart with same attendee email → 0 + 3 > 2
        with pytest.raises(RestrictionViolated):
            validate_restrictions(event, "", attendee_emails=["a@a.com", "a@a.com", "a@a.com"])

    def test_different_attendee_emails_are_independent(self, event):
        event.settings.set("email_restriction_max_per_attendee_email", 2)
        # 2 tickets with a@a.com (ok), 1 ticket with b@b.com (ok) → passes
        validate_restrictions(event, "", attendee_emails=["a@a.com", "a@a.com", "b@b.com"])

    def test_email_comparison_is_case_insensitive(self, event, item):
        event.settings.set("email_restriction_max_per_attendee_email", 1)
        make_order(event, "x@x.com", item, attendee_email="Attendee@Test.COM")
        with pytest.raises(RestrictionViolated):
            validate_restrictions(event, "", attendee_emails=["attendee@test.com"])

    def test_empty_strings_in_list_ignored(self, event):
        event.settings.set("email_restriction_max_per_attendee_email", 1)
        # Empty strings should not trigger the check
        validate_restrictions(event, "", attendee_emails=["", ""])

    def test_exclude_order_avoids_double_counting(self, event, item):
        event.settings.set("email_restriction_max_per_attendee_email", 1)
        order = make_order(event, "x@x.com", item, attendee_email="attendee@test.com")
        # Without exclude: 1 existing + 1 in cart = 2 > 1 → raises
        with pytest.raises(RestrictionViolated):
            validate_restrictions(event, "", attendee_emails=["attendee@test.com"])
        # With exclude (signal scenario): 0 existing + 1 in cart = 1 ≤ 1 → passes
        validate_restrictions(event, "", attendee_emails=["attendee@test.com"], exclude_order=order)

    def test_limit_via_organizer_setting(self, event, organizer, item):
        organizer.settings.set("email_restriction_max_per_attendee_email", 1)
        make_order(event, "x@x.com", item, attendee_email="a@a.com")
        with pytest.raises(RestrictionViolated):
            validate_restrictions(event, "", attendee_emails=["a@a.com"])


# ---------------------------------------------------------------------------
# Both limits active simultaneously
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestBothLimits:
    def test_order_email_limit_blocks(self, event, item):
        event.settings.set("email_restriction_max_per_email", 1)
        event.settings.set("email_restriction_max_per_attendee_email", 100)
        make_order(event, "user@example.com", item)  # 1 order at limit
        with pytest.raises(RestrictionViolated):
            validate_restrictions(event, "user@example.com")

    def test_attendee_email_limit_blocks_when_order_email_passes(self, event, item):
        event.settings.set("email_restriction_max_per_email", 10)
        event.settings.set("email_restriction_max_per_attendee_email", 1)
        make_order(event, "x@x.com", item, attendee_email="attendee@test.com")
        with pytest.raises(RestrictionViolated):
            validate_restrictions(
                event, "user@example.com", attendee_emails=["attendee@test.com"]
            )


# ---------------------------------------------------------------------------
# Custom error message
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestErrorMessage:
    def test_default_message_is_returned(self, event, item):
        event.settings.set("email_restriction_max_per_email", 1)
        make_order(event, "user@example.com", item)
        with pytest.raises(RestrictionViolated) as exc_info:
            validate_restrictions(event, "user@example.com")
        assert len(str(exc_info.value)) > 0

    def test_custom_message_is_used(self, event, item):
        event.settings.set("email_restriction_max_per_email", 1)
        event.settings.set("email_restriction_error_message", "Custom error!")
        make_order(event, "user@example.com", item)
        with pytest.raises(RestrictionViolated) as exc_info:
            validate_restrictions(event, "user@example.com")
        assert "Custom error!" in str(exc_info.value)

    def test_organizer_message_inherited_by_event(self, event, organizer, item):
        organizer.settings.set("email_restriction_max_per_email", 1)
        organizer.settings.set("email_restriction_error_message", "Organizer says no.")
        make_order(event, "user@example.com", item)
        with pytest.raises(RestrictionViolated) as exc_info:
            validate_restrictions(event, "user@example.com")
        assert "Organizer says no." in str(exc_info.value)
