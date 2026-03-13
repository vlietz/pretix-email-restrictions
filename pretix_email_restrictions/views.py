from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views import View

from pretix.control.permissions import (
    EventPermissionRequiredMixin,
    OrganizerPermissionRequiredMixin,
)

from .forms import EventEmailRestrictionForm, OrganizerEmailRestrictionForm
from .restriction import get_effective_setting


class EventEmailRestrictionSettingsView(EventPermissionRequiredMixin, View):
    permission = "can_change_event_settings"

    def _get_form(self, request, data=None):
        return EventEmailRestrictionForm(
            obj=request.event,
            prefix="email_restriction",
            data=data or None,
        )

    def get(self, request, *args, **kwargs):
        form = self._get_form(request)
        allow_override = request.event.organizer.settings.get(
            "email_restriction_allow_event_override", as_type=bool, default=True
        )
        ctx = {
            "form": form,
            "allow_override": allow_override,
            # Show effective (merged) values so the organiser understands inheritance
            "effective_max_per_email": get_effective_setting(
                request.event, "email_restriction_max_per_email", as_type=int
            ),
            "effective_max_per_order": get_effective_setting(
                request.event, "email_restriction_max_per_order", as_type=int
            ),
        }
        return render(request, "pretixcontrol/email_restrictions/event_settings.html", ctx)

    def post(self, request, *args, **kwargs):
        form = self._get_form(request, data=request.POST)
        allow_override = request.event.organizer.settings.get(
            "email_restriction_allow_event_override", as_type=bool, default=True
        )
        if not allow_override:
            messages.warning(
                request,
                _("Event-level overrides are disabled by the organizer. Settings were not saved."),
            )
            return redirect(
                reverse(
                    "plugins:pretix_email_restrictions:settings",
                    kwargs={
                        "organizer": request.organizer.slug,
                        "event": request.event.slug,
                    },
                )
            )
        if form.is_valid():
            form.save()
            messages.success(request, _("Email restriction settings saved."))
            return redirect(
                reverse(
                    "plugins:pretix_email_restrictions:settings",
                    kwargs={
                        "organizer": request.organizer.slug,
                        "event": request.event.slug,
                    },
                )
            )
        ctx = {
            "form": form,
            "allow_override": allow_override,
            "effective_max_per_email": get_effective_setting(
                request.event, "email_restriction_max_per_email", as_type=int
            ),
            "effective_max_per_order": get_effective_setting(
                request.event, "email_restriction_max_per_order", as_type=int
            ),
        }
        return render(request, "pretixcontrol/email_restrictions/event_settings.html", ctx)


class OrganizerEmailRestrictionSettingsView(OrganizerPermissionRequiredMixin, View):
    permission = "can_change_organizer_settings"

    def _get_form(self, request, data=None):
        return OrganizerEmailRestrictionForm(
            obj=request.organizer,
            prefix="email_restriction",
            data=data or None,
        )

    def get(self, request, *args, **kwargs):
        form = self._get_form(request)
        return render(
            request,
            "pretixcontrol/email_restrictions/organizer_settings.html",
            {"form": form},
        )

    def post(self, request, *args, **kwargs):
        form = self._get_form(request, data=request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Email restriction settings saved."))
            return redirect(
                reverse(
                    "plugins:pretix_email_restrictions:organizer.settings",
                    kwargs={"organizer": request.organizer.slug},
                )
            )
        return render(
            request,
            "pretixcontrol/email_restrictions/organizer_settings.html",
            {"form": form},
        )
