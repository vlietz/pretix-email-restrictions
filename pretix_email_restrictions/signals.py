from django.dispatch import receiver
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from django_scopes import scopes_disabled

from pretix.base.signals import order_placed
from pretix.base.services.orders import OrderError
from pretix.control.signals import nav_event_settings, nav_organizer
from pretix.presale.signals import checkout_flow_steps

from .restriction import RestrictionViolated, get_effective_setting, validate_restrictions


# ---------------------------------------------------------------------------
# Checkout step registration
# ---------------------------------------------------------------------------


@receiver(checkout_flow_steps, dispatch_uid="pretix_email_restrictions_checkout_steps")
def register_checkout_step(sender, **kwargs):
    """Return the EmailRestrictionStep class for inclusion in the checkout flow."""
    from .checkoutflow import EmailRestrictionStep

    return EmailRestrictionStep


# ---------------------------------------------------------------------------
# Control-panel navigation
# ---------------------------------------------------------------------------


@receiver(nav_event_settings, dispatch_uid="pretix_email_restrictions_nav_event_settings")
def add_event_settings_nav(sender, request=None, **kwargs):
    """Add a tab to the event settings navigation."""
    url = reverse(
        "plugins:pretix_email_restrictions:settings",
        kwargs={
            "organizer": request.event.organizer.slug,
            "event": request.event.slug,
        },
    )
    return [
        {
            "label": _("Email Restrictions"),
            "url": url,
            "active": request.path.startswith(url),
        }
    ]


@receiver(nav_organizer, dispatch_uid="pretix_email_restrictions_nav_organizer")
def add_organizer_settings_nav(sender, organizer=None, request=None, **kwargs):
    """Add a tab to the organizer navigation."""
    url = reverse(
        "plugins:pretix_email_restrictions:organizer.settings",
        kwargs={"organizer": organizer.slug},
    )
    return [
        {
            "label": _("Email Restrictions"),
            "url": url,
            "active": request.path.startswith(url),
        }
    ]


# ---------------------------------------------------------------------------
# API / direct order creation validation
# ---------------------------------------------------------------------------


@receiver(order_placed, dispatch_uid="pretix_email_restrictions_order_placed")
def validate_order_on_placement(sender, order, **kwargs):
    """
    Validate email restrictions when an order is placed.

    For orders created through the standard checkout flow the
    EmailRestrictionStep already blocks invalid orders before this point.
    This receiver acts as a safety net and as the enforcement mechanism
    for orders created directly via the REST API.

    ``order_placed`` fires inside the same database transaction as order
    creation.  Raising ``OrderError`` here causes pretix to roll back the
    transaction and return an error to the caller (HTTP 400 for API requests).
    """
    event = sender

    has_order_limit = get_effective_setting(event, "email_restriction_max_per_email", as_type=int)
    has_attendee_limit = get_effective_setting(
        event, "email_restriction_max_per_attendee_email", as_type=int
    )
    if not has_order_limit and not has_attendee_limit:
        return

    # Exclude the new order itself to avoid double-counting
    # (the order is already persisted when this signal fires).
    with scopes_disabled():
        positions = list(order.positions.all())
    order_email = order.email or ""
    attendee_emails = [p.attendee_email for p in positions if p.attendee_email]

    try:
        validate_restrictions(
            event,
            order_email,
            exclude_order=order,
            attendee_emails=attendee_emails,
        )
    except RestrictionViolated as exc:
        raise OrderError(str(exc)) from exc
