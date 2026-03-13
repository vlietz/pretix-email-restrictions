"""
Core restriction logic shared between the checkout step and the order_placed signal.
"""
from django.utils.translation import gettext_lazy as _
from django_scopes import scopes_disabled

from pretix.base.models import Order, OrderPosition


class RestrictionViolated(Exception):
    """Raised when an email or order restriction is violated."""


def get_effective_setting(event, key, as_type=None):
    """
    Return the setting value respecting the organizer → event override hierarchy.

    If the organizer has disabled event-level overrides
    (``email_restriction_allow_event_override = False``), the organizer value
    is always used.  Otherwise the event value takes precedence when set.
    """
    allow_override = event.organizer.settings.get(
        "email_restriction_allow_event_override",
        as_type=bool,
        default=True,
    )
    if allow_override:
        val = event.settings.get(key, as_type=as_type)
        if val is not None:
            return val
    return event.organizer.settings.get(key, as_type=as_type)


def get_error_message(event):
    msg = get_effective_setting(event, "email_restriction_error_message")
    if not msg:
        msg = str(_("You have reached the maximum number of tickets allowed for this event."))
    return msg


def count_existing_tickets(event, email, exclude_order=None):
    """
    Count OrderPositions for *email* in *event* that are still active
    (pending or paid).  Cancelled and expired orders are excluded.

    Pass ``exclude_order`` to avoid double-counting the order that is
    currently being validated (used in the order_placed signal handler).
    """
    with scopes_disabled():
        qs = OrderPosition.objects.filter(
            order__event=event,
            order__email__iexact=email.strip(),
            order__status__in=[Order.STATUS_PENDING, Order.STATUS_PAID],
        )
        if exclude_order is not None:
            qs = qs.exclude(order=exclude_order)
        return qs.count()


def validate_restrictions(event, email, cart_count, exclude_order=None):
    """
    Validate both the per-order and the per-email limits.

    Raises ``RestrictionViolated`` with a human-readable message if either
    limit is exceeded.

    Args:
        event:          The ``Event`` being booked.
        email:          The customer's email address (may be empty string).
        cart_count:     Number of ticket positions in the current cart / order.
        exclude_order:  ``Order`` instance to exclude from the existing-ticket
                        count (supply the just-created order when called from
                        the ``order_placed`` signal).
    """
    max_per_order = get_effective_setting(event, "email_restriction_max_per_order", as_type=int)
    if max_per_order is not None and cart_count > max_per_order:
        raise RestrictionViolated(get_error_message(event))

    max_per_email = get_effective_setting(event, "email_restriction_max_per_email", as_type=int)
    if max_per_email is not None and email:
        existing = count_existing_tickets(event, email, exclude_order=exclude_order)
        if existing + cart_count > max_per_email:
            raise RestrictionViolated(get_error_message(event))
