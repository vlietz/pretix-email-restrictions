"""
Custom checkout step that validates per-email ticket limits.

This step is inserted after QuestionsStep (priority 50) so that the customer
has already entered their email address before the check runs.
Priority 55 places it just after questions and before PaymentStep (200).

Forward navigation (no errors): the step is transparent — it auto-redirects
to the next step and records that it was passed in the cart session.

Backward navigation (back button on review/payment page): the cart session
flag indicates the user is navigating back, so the step renders its
"all clear" template instead of looping forward.

Error case: always renders the error template and clears the session flag.
"""
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _

from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.checkoutflow import TemplateFlowStep
from pretix.presale.views import CartMixin

from .restriction import RestrictionViolated, get_effective_setting, validate_restrictions

_SESSION_KEY = "email_restriction_step_seen"


class EmailRestrictionStep(CartMixin, TemplateFlowStep):
    identifier = "email_restriction"
    priority = 55  # after QuestionsStep (50), before PaymentStep (200)
    template_name = "pretix_email_restrictions/checkout_restriction.html"

    @property
    def label(self):
        return _("Email restriction check")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _cart_session(self, request):
        from pretix.presale.views.cart import cart_session
        return cart_session(request)

    def _cart_id(self, request):
        from pretix.presale.views.cart import get_or_create_cart_id
        return get_or_create_cart_id(request)

    def _cart_attendee_emails(self, request):
        """Return all attendee email addresses from current cart positions."""
        from pretix.base.models import CartPosition
        positions = CartPosition.objects.filter(
            event=self.event,
            cart_id=self._cart_id(request),
        )
        return [p.attendee_email for p in positions if p.attendee_email]

    def _get_errors(self, request):
        """Return a list of error strings; empty list means everything is fine."""
        has_order_limit = get_effective_setting(
            self.event, "email_restriction_max_per_email", as_type=int
        )
        has_attendee_limit = get_effective_setting(
            self.event, "email_restriction_max_per_attendee_email", as_type=int
        )
        if not has_order_limit and not has_attendee_limit:
            return []

        order_email = self._cart_session(request).get("email", "").strip()
        attendee_emails = self._cart_attendee_emails(request)

        try:
            validate_restrictions(
                self.event,
                order_email,
                attendee_emails=attendee_emails,
            )
        except RestrictionViolated as exc:
            return [str(exc)]
        return []

    def _button_label(self, key, default):
        val = get_effective_setting(self.event, key)
        return val if val else str(default)

    def _questions_url(self):
        return eventreverse(
            self.event,
            "presale:event.checkout",
            kwargs={"step": "questions"},
        )

    # ------------------------------------------------------------------
    # BaseCheckoutFlowStep interface
    # ------------------------------------------------------------------

    def is_applicable(self, request):
        return bool(
            get_effective_setting(self.event, "email_restriction_max_per_email", as_type=int)
            or get_effective_setting(
                self.event, "email_restriction_max_per_attendee_email", as_type=int
            )
        )

    def is_completed(self, request, warn=False):
        return len(self._get_errors(request)) == 0

    def get_step_url(self, request):
        kwargs = {"step": self.identifier}
        if request.resolver_match and "cart_namespace" in request.resolver_match.kwargs:
            kwargs["cart_namespace"] = request.resolver_match.kwargs["cart_namespace"]
        return eventreverse(self.event, "presale:event.checkout", kwargs=kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        errors = self._get_errors(self.request)
        ctx["errors"] = errors
        ctx["cart"] = self.get_cart()
        ctx["cart_url"] = eventreverse(self.event, "presale:event.index")
        ctx["questions_url"] = self._questions_url()
        ctx["back_to_cart_label"] = self._button_label(
            "email_restriction_back_to_cart_label", _("Back to ticket selection")
        )
        ctx["change_email_label"] = self._button_label(
            "email_restriction_change_email_label", _("Change email address")
        )
        return ctx

    def get(self, request):
        self.request = request
        errors = self._get_errors(request)

        if errors:
            # Restriction violated — show error page and clear the seen-flag so
            # the next forward pass will auto-redirect again once the user fixes
            # their order.
            cs = self._cart_session(request)
            cs.pop(_SESSION_KEY, None)
            return self.render()

        cs = self._cart_session(request)
        if cs.get(_SESSION_KEY):
            # User navigated back to this step from a later step.
            # Show the "all clear" template so back-navigation works naturally.
            return self.render()

        # First forward pass with no errors: skip transparently and record it.
        cs[_SESSION_KEY] = True
        next_step = self.get_next_applicable(request)
        if next_step:
            return redirect(next_step.get_step_url(request))
        return self.render()

    def post(self, request):
        self.request = request

        # "Change email address": clear order email so the user can re-enter it.
        if request.POST.get("action") == "change_email":
            cs = self._cart_session(request)
            cs.pop("email", None)
            cs.pop(_SESSION_KEY, None)
            return redirect(self._questions_url())

        errors = self._get_errors(request)
        if not errors:
            # User clicked "Continue" on the "all clear" panel.
            # Clear the flag so a subsequent forward pass is transparent again.
            cs = self._cart_session(request)
            cs.pop(_SESSION_KEY, None)
            next_step = self.get_next_applicable(request)
            if next_step:
                return redirect(next_step.get_step_url(request))
        return self.render()
