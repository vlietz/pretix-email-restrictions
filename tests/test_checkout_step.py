"""
Tests for the EmailRestrictionStep checkout flow step.

These tests verify that the step's is_applicable / is_completed methods
behave correctly given the current DB state and cart session.
"""
from unittest.mock import patch

import pytest

from pretix.base.models import Order

from pretix_email_restrictions.checkoutflow import EmailRestrictionStep

from .conftest import make_order


def make_request(event, email=""):
    """Build a minimal fake request with a cart session."""
    from unittest.mock import MagicMock

    request = MagicMock()
    request.event = event
    request.organizer = event.organizer
    request.resolver_match = MagicMock()
    request.resolver_match.kwargs = {}
    request._mock_cart_session = {"email": email}
    return request


def make_step(event, request, cart_id="test-cart-id"):
    """Instantiate EmailRestrictionStep with mocked cart session/id."""
    step = EmailRestrictionStep(event=event)
    step.request = request

    def fake_cart_session(_request):
        return request._mock_cart_session

    def fake_cart_id(_request):
        return cart_id

    step._cart_session = fake_cart_session  # type: ignore[method-assign]
    step._cart_id = fake_cart_id  # type: ignore[method-assign]
    return step


# ---------------------------------------------------------------------------
# is_applicable
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestIsApplicable:
    def test_not_applicable_when_no_limits_set(self, event):
        step = EmailRestrictionStep(event=event)
        request = make_request(event)
        assert step.is_applicable(request) is False

    def test_applicable_when_per_email_set(self, event):
        event.settings.set("email_restriction_max_per_email", 3)
        step = EmailRestrictionStep(event=event)
        request = make_request(event)
        assert step.is_applicable(request) is True

    def test_applicable_when_per_attendee_set(self, event):
        event.settings.set("email_restriction_max_per_attendee_email", 2)
        step = EmailRestrictionStep(event=event)
        request = make_request(event)
        assert step.is_applicable(request) is True

    def test_applicable_via_organizer_setting(self, event, organizer):
        organizer.settings.set("email_restriction_max_per_email", 5)
        step = EmailRestrictionStep(event=event)
        request = make_request(event)
        assert step.is_applicable(request) is True


# ---------------------------------------------------------------------------
# is_completed
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestIsCompleted:
    def test_completed_when_no_limits(self, event):
        step = EmailRestrictionStep(event=event)
        request = make_request(event, email="user@example.com")
        assert step.is_completed(request) is True

    def test_completed_when_under_order_email_limit(self, event, item):
        """2 existing orders with limit=5 → 2 < 5 → completed."""
        event.settings.set("email_restriction_max_per_email", 5)
        make_order(event, "user@example.com", item)
        make_order(event, "user@example.com", item)

        request = make_request(event, email="user@example.com")
        step = make_step(event, request)

        with patch.object(step, "_cart_attendee_emails", return_value=[]):
            assert step.is_completed(request) is True

    def test_not_completed_when_at_order_email_limit(self, event, item):
        """2 existing orders with limit=2 → 2 >= 2 → not completed."""
        event.settings.set("email_restriction_max_per_email", 2)
        make_order(event, "user@example.com", item)
        make_order(event, "user@example.com", item)

        request = make_request(event, email="user@example.com")
        step = make_step(event, request)

        with patch.object(step, "_cart_attendee_emails", return_value=[]):
            assert step.is_completed(request) is False

    def test_not_completed_when_over_attendee_email_limit(self, event, item):
        """1 existing attendee ticket + 1 in cart, limit=1 → 2 > 1 → not completed."""
        event.settings.set("email_restriction_max_per_attendee_email", 1)
        make_order(event, "x@x.com", item, attendee_email="attendee@test.com")

        request = make_request(event, email="user@example.com")
        step = make_step(event, request)

        with patch.object(step, "_cart_attendee_emails", return_value=["attendee@test.com"]):
            assert step.is_completed(request) is False

    def test_completed_when_email_missing_and_only_per_email_limit(self, event):
        """
        No email in session yet → per-email check is skipped.
        (Customer hasn't filled in the questions step.)
        """
        event.settings.set("email_restriction_max_per_email", 1)

        request = make_request(event, email="")
        step = make_step(event, request)

        with patch.object(step, "_cart_attendee_emails", return_value=[]):
            assert step.is_completed(request) is True

    def test_cancelled_orders_do_not_count(self, event, item):
        event.settings.set("email_restriction_max_per_email", 1)
        make_order(event, "user@example.com", item, status=Order.STATUS_CANCELED)

        request = make_request(event, email="user@example.com")
        step = make_step(event, request)

        with patch.object(step, "_cart_attendee_emails", return_value=[]):
            # Cancelled order → 0 active orders < 1 → completed
            assert step.is_completed(request) is True


# ---------------------------------------------------------------------------
# Step metadata
# ---------------------------------------------------------------------------


def test_step_identifier(event):
    step = EmailRestrictionStep(event=event)
    assert step.identifier == "email_restriction"


def test_step_priority_between_questions_and_payment(event):
    step = EmailRestrictionStep(event=event)
    # Must run AFTER QuestionsStep (priority 50)
    assert step.priority > 50
    # Must run BEFORE PaymentStep (priority 200)
    assert step.priority < 200
