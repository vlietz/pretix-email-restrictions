from django import forms
from django.utils.translation import gettext_lazy as _

from pretix.base.forms import SettingsForm


class OrganizerEmailRestrictionForm(SettingsForm):
    """
    Settings stored at organizer level.
    These are the defaults that individual events may override (if allowed).
    """

    email_restriction_max_per_email = forms.IntegerField(
        min_value=1,
        required=False,
        label=_("Maximum tickets per email address"),
        help_text=_(
            "The maximum total number of tickets that one email address may hold "
            "for a single event (counting all pending and paid orders). "
            "Leave empty to disable this limit."
        ),
    )
    email_restriction_max_per_order = forms.IntegerField(
        min_value=1,
        required=False,
        label=_("Maximum tickets per order"),
        help_text=_(
            "The maximum number of tickets that may be placed in a single order. "
            "Leave empty to disable this limit."
        ),
    )
    email_restriction_error_message = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        label=_("Error message"),
        help_text=_(
            "Message shown to the customer when a limit is exceeded. "
            "Leave empty to use the default message."
        ),
    )
    email_restriction_allow_event_override = forms.BooleanField(
        required=False,
        label=_("Allow individual events to override these defaults"),
        help_text=_(
            "When enabled, event organizers can set different limits per event. "
            "When disabled, only the values set here apply to all events."
        ),
    )


class EventEmailRestrictionForm(SettingsForm):
    """
    Settings stored at event level.
    Only effective when the organizer has allowed event-level overrides.
    """

    email_restriction_max_per_email = forms.IntegerField(
        min_value=1,
        required=False,
        label=_("Maximum tickets per email address"),
        help_text=_(
            "Overrides the organizer default for this event. "
            "Leave empty to inherit the organizer setting."
        ),
    )
    email_restriction_max_per_order = forms.IntegerField(
        min_value=1,
        required=False,
        label=_("Maximum tickets per order"),
        help_text=_(
            "Overrides the organizer default for this event. "
            "Leave empty to inherit the organizer setting."
        ),
    )
    email_restriction_error_message = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        label=_("Error message"),
        help_text=_(
            "Overrides the organizer default error message for this event. "
            "Leave empty to inherit the organizer setting."
        ),
    )
