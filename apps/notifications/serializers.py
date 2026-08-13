"""Notification serializers."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.notifications.models import Notification, NotificationPreference


class NotificationSerializer(serializers.ModelSerializer):
    """One in-app notification as the bell menu renders it."""

    id = serializers.UUIDField(source="uuid", read_only=True)
    category_display = serializers.CharField(
        source="get_category_display", read_only=True
    )

    class Meta:
        model = Notification
        fields = (
            "id",
            "event",
            "category",
            "category_display",
            "subject",
            "body",
            "link",
            "is_read",
            "read_at",
            "created_at",
        )
        read_only_fields = fields


class UnreadCountSerializer(serializers.Serializer):
    """The number on the bell icon."""

    unread = serializers.IntegerField(read_only=True)


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    """A customer's opt-outs.

    ``push_token`` is write-only: the frontend sets it and never needs it back,
    and echoing a device token into a response body puts it in every log that
    captures responses.
    """

    push_token = serializers.CharField(
        max_length=255, required=False, allow_blank=True, write_only=True
    )
    has_push_token = serializers.SerializerMethodField()

    class Meta:
        model = NotificationPreference
        fields = (
            "email_enabled",
            "sms_enabled",
            "push_enabled",
            "marketing_enabled",
            "push_token",
            "has_push_token",
        )

    def get_has_push_token(self, obj: NotificationPreference) -> bool:
        """Report whether a device is registered, without revealing the token."""
        return bool(obj.push_token)


class NotificationAdminSerializer(serializers.ModelSerializer):
    """A notification as staff see it — including the delivery ledger fields."""

    id = serializers.UUIDField(source="uuid", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Notification
        fields = (
            "id",
            "user_email",
            "event",
            "category",
            "channel",
            "subject",
            "status",
            "attempts",
            "error",
            "sent_at",
            "created_at",
        )
        read_only_fields = fields


class NotificationStatsSerializer(serializers.Serializer):
    """Delivery counters for the admin dashboard."""

    total = serializers.IntegerField(read_only=True)
    pending = serializers.IntegerField(read_only=True)
    failed = serializers.IntegerField(read_only=True)
    by_status = serializers.DictField(read_only=True)
    by_channel = serializers.DictField(read_only=True)


class QueueResultSerializer(serializers.Serializer):
    """What a queue drain or retry pass did."""

    processed = serializers.IntegerField(read_only=True)
    sent = serializers.IntegerField(read_only=True)
    failed = serializers.IntegerField(read_only=True)
