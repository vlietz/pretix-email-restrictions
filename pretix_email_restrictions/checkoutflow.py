"""
Custom checkout step that validates email and per-order ticket limits.

This step is inserted between QuestionsStep (priority 50) and PaymentStep
so that the customer has already entered their email address before the
check runs.  Priority 45 places it just after questions.
"""
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.checkoutflow import BaseCheckoutFlowStep

from .restriction import RestrictionViolated, get_effective_setting, validate_restrictions


class EmailRestrictionStep(BaseCheckoutFlowStep):
    identifier = "email_restriction"
    priority = 45  # QuestionsStep = 50, PaymentStep < 20

    @property
    def label(self):
        return _("Email restriction check")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _cart_session(self, request):
        """Return the cart session dict for the current request."""
        from pretix.presale.views.cart import cart_session
        return cart_session(request)

    def _cart_id(self, request):
        from pretix.presale.views.cart import get_or_create_cart_id
        return get_or_create_cart_id(request)

    def _cart_count(self, request):
        from pretix.base.models import CartPosition
        return CartPosition.objects.filter(
            event=self.event,
            cart_id=self._cart_id(request),
        ).count()

    def _get_errors(self, request):
        """Return a list of error strings; empty means everything is fine."""
        # Fast-exit: no limits configured → nothing to check
        has_per_email = get_effective_setting(
            self.event, "email_restriction_max_per_email", as_type=int
        )
        has_per_order = get_effective_setting(
            self.event, "email_restriction_max_per_order", as_type=int
        )
        if not has_per_email and not has_per_order:
            return []

        email = self._cart_session(request).get("email", "").strip()
        cart_count = self._cart_count(request)

        try:
            validate_restrictions(self.event, email, cart_count)
        except RestrictionViolated as exc:
            return [str(exc)]
        return []

    # ------------------------------------------------------------------
    # BaseCheckoutFlowStep interface
    # ------------------------------------------------------------------

    def is_applicable(self, request):
        return bool(
            get_effective_setting(self.event, "email_restriction_max_per_email", as_type=int)
            or get_effective_setting(self.event, "email_restriction_max_per_order", as_type=int)
        )

    def is_completed(self, request, warn=False):
        return len(self._get_errors(request)) == 0

    def get_step_url(self, request):
        kwargs = {"step": self.identifier}
        if request.resolver_match and "cart_namespace" in request.resolver_match.kwargs:
            kwargs["cart_namespace"] = request.resolver_match.kwargs["cart_namespace"]
        return eventreverse(self.event, "presale:event.checkout", kwargs=kwargs)

    def get(self, request):
        ctx = {
            "request": request,
            "event": self.event,
            "errors": self._get_errors(request),
            # URL to go back and change the number of tickets
            "cart_url": eventreverse(self.event, "presale:event.index"),
            # URL to go back and change the email address
            "questions_url": eventreverse(
                self.event,
                "presale:event.checkout",
                kwargs={"step": "questions"},
            ),
        }
        return render(request, "pretix_email_restrictions/checkout_restriction.html", ctx)

    def post(self, request):
        """
        There is no form on this page; the user can only go back.
        If somehow the limits are now satisfied (e.g., another tab modified
        the cart), proceed to the next step.
        """
        errors = self._get_errors(request)
        if not errors:
            next_step = self.get_next_applicable(request)
            if next_step:
                return redirect(next_step.get_step_url(request))
        return self.get(request)
