"""
Tests for the EmailRestrictionStep checkout flow step.

These tests verify that the step's is_applicable / is_completed methods
behave correctly and that the step renders an error page when limits are
exceeded.
"""
from unittest.mock import MagicMock, patch

import pytest

from pretix.base.models import CartPosition, Order

from pretix_email_restrictions.checkoutflow import EmailRestrictionStep

from .conftest import make_order


def make_request(event, email="", cart_positions=None):
    """
    Build a minimal fake request with a cart session and CartPosition
    objects in the database.
    """
    cart_positions = cart_positions or []

    request = MagicMock()
    request.event = event
    request.organizer = event.organizer
    request.resolver_match = MagicMock()
    request.resolver_match.kwargs = {}

    # The step calls cart_session(request) which reads from the Django session.
    # We mock it to return a simple dict.
    request._mock_cart_session = {"email": email}

    return request


def make_step(event, request, cart_id="test-cart-id"):
    """Instantiate EmailRestrictionStep with a mocked cart session."""
    step = EmailRestrictionStep(event=event)
    step.request = request

    # Patch cart_session import used inside the step
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

    def test_applicable_when_per_order_set(self, event):
        event.settings.set("email_restriction_max_per_order", 2)
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
    def _make_cart_positions(self, event, n, cart_id="test-cart"):
        """Create n CartPosition rows for the given cart_id."""
        positions = []
        for _ in range(n):
            pos = CartPosition(
                event=event,
                cart_id=cart_id,
                price=10,
                expires=CartPosition._meta.get_field("expires").default,
            )
            positions.append(pos)
        CartPosition.objects.bulk_create(positions)
        return positions

    def test_completed_when_no_limits(self, event):
        step = EmailRestrictionStep(event=event)
        request = make_request(event, email="user@example.com")
        assert step.is_completed(request) is True

    def test_completed_when_under_per_email_limit(self, event, item):
        event.settings.set("email_restriction_max_per_email", 5)
        make_order(event, "user@example.com", item, n_positions=2)

        request = make_request(event, email="user@example.com")
        step = make_step(event, request, cart_id="cart1")

        with patch.object(step, "_cart_count", return_value=2):
            assert step.is_completed(request) is True

    def test_not_completed_when_over_per_email_limit(self, event, item):
        event.settings.set("email_restriction_max_per_email", 3)
        make_order(event, "user@example.com", item, n_positions=2)

        request = make_request(event, email="user@example.com")
        step = make_step(event, request, cart_id="cart1")

        with patch.object(step, "_cart_count", return_value=2):
            assert step.is_completed(request) is False

    def test_not_completed_when_over_per_order_limit(self, event):
        event.settings.set("email_restriction_max_per_order", 2)

        request = make_request(event, email="user@example.com")
        step = make_step(event, request, cart_id="cart1")

        with patch.object(step, "_cart_count", return_value=3):
            assert step.is_completed(request) is False

    def test_completed_when_email_missing_and_only_per_email_limit(self, event):
        """
        No email in session yet means the per-email check should not fire.
        (The customer hasn't filled in the questions step.)
        """
        event.settings.set("email_restriction_max_per_email", 1)

        request = make_request(event, email="")
        step = make_step(event, request)

        with patch.object(step, "_cart_count", return_value=1):
            assert step.is_completed(request) is True

    def test_cancelled_orders_do_not_count(self, event, item):
        event.settings.set("email_restriction_max_per_email", 2)
        make_order(event, "user@example.com", item, n_positions=2, status=Order.STATUS_CANCELED)

        request = make_request(event, email="user@example.com")
        step = make_step(event, request)

        with patch.object(step, "_cart_count", return_value=2):
            assert step.is_completed(request) is True


# ---------------------------------------------------------------------------
# Step metadata
# ---------------------------------------------------------------------------


def test_step_identifier(event):
    step = EmailRestrictionStep(event=event)
    assert step.identifier == "email_restriction"


def test_step_priority_between_questions_and_payment(event):
    step = EmailRestrictionStep(event=event)
    # QuestionsStep.priority == 50, our step must be lower (runs after)
    assert step.priority < 50
    # PaymentStep is around 20; we want to be before payment
    assert step.priority > 20
