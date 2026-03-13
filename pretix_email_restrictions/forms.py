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
        label=_("Maximum orders per order email"),
        help_text=_(
            "How many orders a single email address may place for this event "
            "(counting pending and paid orders). The number of tickets per order "
            "does not matter — a fresh email always passes. "
            "Leave empty to disable this limit."
        ),
    )
    email_restriction_max_per_attendee_email = forms.IntegerField(
        min_value=1,
        required=False,
        label=_("Maximum tickets per attendee email"),
        help_text=_(
            "The maximum number of tickets a single email address may appear on "
            "as the attendee email, across all orders for this event (including "
            "multiple tickets within the same order). Leave empty to disable this limit."
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
    email_restriction_back_to_cart_label = forms.CharField(
        required=False,
        label=_("'Back to ticket selection' button label"),
        help_text=_("Leave empty to use the default label."),
    )
    email_restriction_change_email_label = forms.CharField(
        required=False,
        label=_("'Change email address' button label"),
        help_text=_("Leave empty to use the default label."),
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
        label=_("Maximum orders per order email"),
        help_text=_(
            "Overrides the organizer default for this event. "
            "How many orders a single email address may place. "
            "Leave empty to inherit the organizer setting."
        ),
    )
    email_restriction_max_per_attendee_email = forms.IntegerField(
        min_value=1,
        required=False,
        label=_("Maximum tickets per attendee email"),
        help_text=_(
            "Overrides the organizer default for this event. "
            "The maximum number of tickets a single email address may appear on as the "
            "attendee email (across all orders, including within the same order). "
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
    email_restriction_back_to_cart_label = forms.CharField(
        required=False,
        label=_("'Back to ticket selection' button label"),
        help_text=_("Leave empty to inherit the organizer setting or use the default."),
    )
    email_restriction_change_email_label = forms.CharField(
        required=False,
        label=_("'Change email address' button label"),
        help_text=_("Leave empty to inherit the organizer setting or use the default."),
    )
