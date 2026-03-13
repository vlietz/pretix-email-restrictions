"""
Core restriction logic shared between the checkout step and the order_placed signal.
"""
from collections import Counter

from django.utils.translation import gettext_lazy as _
from django_scopes import scopes_disabled

from pretix.base.models import Order, OrderPosition


class RestrictionViolated(Exception):
    """Raised when a per-email limit is violated."""


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


def count_existing_orders_by_email(event, email, exclude_order=None):
    """
    Count how many pending/paid Orders for *event* have *email* as the order email.

    This is used for the order-email limit: the limit controls how many
    *orders* (not tickets) a given email address may place for this event.
    """
    with scopes_disabled():
        qs = Order.objects.filter(
            event=event,
            email__iexact=email.strip(),
            status__in=[Order.STATUS_PENDING, Order.STATUS_PAID],
        )
        if exclude_order is not None:
            qs = qs.exclude(pk=exclude_order.pk)
        return qs.count()


def count_existing_tickets_by_attendee_email(event, attendee_email, exclude_order=None):
    """
    Count OrderPositions where the attendee email on the position matches
    *attendee_email*.

    Only pending and paid orders are counted; cancelled/expired are excluded.
    """
    with scopes_disabled():
        qs = OrderPosition.objects.filter(
            order__event=event,
            attendee_email__iexact=attendee_email.strip(),
            order__status__in=[Order.STATUS_PENDING, Order.STATUS_PAID],
        )
        if exclude_order is not None:
            qs = qs.exclude(order=exclude_order)
        return qs.count()


def validate_restrictions(event, order_email, exclude_order=None, attendee_emails=None):
    """
    Validate all configured per-email limits.

    Raises ``RestrictionViolated`` with a human-readable message on the first
    violated limit.

    Args:
        event:           The ``Event`` being booked.
        order_email:     The customer's order-level email address (may be empty).
        exclude_order:   ``Order`` instance to exclude from counts (supply the
                         just-created order when called from the order_placed signal).
        attendee_emails: List of per-position attendee email addresses from the
                         current cart or order (may be None or contain empty strings).
    """
    # ------------------------------------------------------------------
    # 1. Order-email limit: counts how many *orders* this email has placed.
    #    Cart size is irrelevant — a fresh email always passes.
    # ------------------------------------------------------------------
    max_per_order_email = get_effective_setting(
        event, "email_restriction_max_per_email", as_type=int
    )
    if max_per_order_email is not None and order_email:
        existing_orders = count_existing_orders_by_email(
            event, order_email, exclude_order=exclude_order
        )
        if existing_orders >= max_per_order_email:
            raise RestrictionViolated(get_error_message(event))

    # ------------------------------------------------------------------
    # 2. Attendee-email limit: counts how many *tickets* each attendee
    #    email appears on, across all orders including the current cart.
    # ------------------------------------------------------------------
    max_per_attendee_email = get_effective_setting(
        event, "email_restriction_max_per_attendee_email", as_type=int
    )
    if max_per_attendee_email is not None and attendee_emails:
        # Tally how many times each attendee email appears in the current cart.
        cart_email_counts = Counter(
            e.strip().lower() for e in attendee_emails if e and e.strip()
        )
        for attendee_email, cart_email_count in cart_email_counts.items():
            existing = count_existing_tickets_by_attendee_email(
                event, attendee_email, exclude_order=exclude_order
            )
            if existing + cart_email_count > max_per_attendee_email:
                raise RestrictionViolated(get_error_message(event))
