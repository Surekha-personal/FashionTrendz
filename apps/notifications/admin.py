"""Django admin for notifications."""

from __future__ import annotations

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.notifications import services
from apps.notifications.models import (
    Notification,
    NotificationPreference,
    NotificationStatus,
)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """The delivery ledger.

    Read-only. Every field is either what was sent or what the provider said
    about it; editing any of them would make the ledger a record of what
    someone typed rather than of what happened.
    """

    list_display = (
        "id",
        "user",
        "event",
        "channel",
        "status_pill",
        "subject",
        "attempts",
        "sent_at",
        "created_at",
    )
    list_filter = ("status", "channel", "category", "created_at")
    search_fields = ("user__email", "event", "subject", "error")
    raw_id_fields = ("user",)
    readonly_fields = [field.name for field in Notification._meta.fields]
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_per_page = 50
    actions = ("resend_selected",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Notifications are produced by events, never typed in."""
        return False

    def has_change_permission(self, request: HttpRequest, obj: object = None) -> bool:
        """The ledger records what was sent; it is not editable."""
        return False

    def get_queryset(self, request: HttpRequest) -> QuerySet[Notification]:
        """Join the recipient shown in every row."""
        return super().get_queryset(request).select_related("user")

    @admin.display(description=_("status"), ordering="status")
    def status_pill(self, obj: Notification) -> str:
        """Colour the status so a failed batch is visible at a glance."""
        colour = {
            NotificationStatus.SENT: "#0a7d33",
            NotificationStatus.DELIVERED: "#0a7d33",
            NotificationStatus.PENDING: "#9a6700",
            NotificationStatus.FAILED: "#b3261e",
        }.get(obj.status, "#444")
        return format_html(
            '<b style="color:{}">{}</b>', colour, obj.get_status_display()
        )

    @admin.action(description=_("Resend selected notifications"))
    def resend_selected(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Re-attempt delivery for the selected rows.

        Reset to pending first, so a row that already exhausted its attempts is
        genuinely retried rather than skipped by the retry filter.
        """
        rows = list(queryset.select_related("user"))
        for notification in rows:
            notification.status = NotificationStatus.PENDING
        sent = sum(1 for row in rows if services.send_notification(row))
        self.message_user(
            request, f"{sent} of {len(rows)} resent.", messages.SUCCESS
        )


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    """A customer's opt-outs, for support to inspect and correct."""

    list_display = (
        "user",
        "email_enabled",
        "sms_enabled",
        "push_enabled",
        "marketing_enabled",
        "has_device",
        "updated_at",
    )
    list_filter = (
        "email_enabled",
        "sms_enabled",
        "push_enabled",
        "marketing_enabled",
    )
    search_fields = ("user__email",)
    raw_id_fields = ("user",)
    readonly_fields = ("uuid", "created_at", "updated_at")

    def get_queryset(self, request: HttpRequest) -> QuerySet[NotificationPreference]:
        """Join the customer shown in every row."""
        return super().get_queryset(request).select_related("user")

    @admin.display(description=_("device"), boolean=True)
    def has_device(self, obj: NotificationPreference) -> bool:
        """Report whether a push token is registered, without printing it."""
        return bool(obj.push_token)
