"""Notification API views. Thin by construction."""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.pagination import StandardPagination
from apps.core.permissions import IsAdmin
from apps.core.responses import success_response
from apps.core.throttling import NotificationQueueThrottle
from apps.notifications import services
from apps.notifications.models import Notification
from apps.notifications.serializers import (
    NotificationAdminSerializer,
    NotificationPreferenceSerializer,
    NotificationSerializer,
    NotificationStatsSerializer,
    QueueResultSerializer,
    UnreadCountSerializer,
)


@extend_schema(tags=["Notifications"])
class NotificationViewSet(viewsets.GenericViewSet):
    """A customer's in-app inbox."""

    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    serializer_class = NotificationSerializer
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"
    queryset = Notification.objects.none()

    def get_queryset(self) -> Any:
        """Return the caller's inbox, optionally unread only."""
        unread = str(self.request.query_params.get("unread", "")).lower() in {
            "1",
            "true",
            "yes",
        }
        return services.get_inbox(self.request.user, unread_only=unread)

    @extend_schema(
        summary="List my notifications",
        parameters=[OpenApiParameter("unread", bool, description="Unread only.")],
        responses={200: NotificationSerializer(many=True)},
    )
    def list(self, request: Request) -> Response:
        """Return the in-app notification list."""
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(
            page if page is not None else queryset, many=True
        )
        if page is not None:
            response = self.get_paginated_response(serializer.data)
            response.message = "Notifications retrieved."
            return response
        return success_response(serializer.data, message="Notifications retrieved.")

    @extend_schema(summary="Unread count", responses={200: UnreadCountSerializer})
    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request: Request) -> Response:
        """Return the number on the bell icon."""
        return success_response(
            {"unread": services.unread_count(request.user)},
            message="Unread count retrieved.",
        )

    @extend_schema(summary="Mark one read", responses={200: None})
    @action(detail=True, methods=["post"], url_path="read", url_name="read")
    def mark_read(self, request: Request, uuid: str) -> Response:
        """Mark one notification read."""
        changed = services.mark_read(request.user, uuid)
        return success_response({"updated": changed}, message="Notification read.")

    @extend_schema(summary="Mark all read", responses={200: None})
    @action(
        detail=False, methods=["post"], url_path="read-all", url_name="read-all"
    )
    def mark_all_read(self, request: Request) -> Response:
        """Empty the unread badge in one update."""
        return success_response(
            {"updated": services.mark_all_read(request.user)},
            message="All notifications marked read.",
        )

    @extend_schema(summary="Delete one notification", responses={200: None})
    def destroy(self, request: Request, uuid: str) -> Response:
        """Remove one notification from the inbox."""
        return success_response(
            {"deleted": services.delete_notification(request.user, uuid)},
            message="Notification deleted.",
        )

    @extend_schema(
        summary="My notification preferences",
        responses={200: NotificationPreferenceSerializer},
    )
    @action(
        detail=False,
        methods=["get", "patch"],
        url_path="preferences",
        url_name="preferences",
    )
    def preferences(self, request: Request) -> Response:
        """Read or update the caller's opt-outs."""
        if request.method == "GET":
            preference = services.get_preference(request.user)
            return success_response(
                NotificationPreferenceSerializer(preference).data,
                message="Preferences retrieved.",
            )

        payload = NotificationPreferenceSerializer(data=request.data, partial=True)
        payload.is_valid(raise_exception=True)
        preference = services.update_preference(request.user, **payload.validated_data)
        return success_response(
            NotificationPreferenceSerializer(preference).data,
            message="Preferences updated.",
        )


@extend_schema(tags=["Notifications — Admin"])
class NotificationAdminViewSet(viewsets.GenericViewSet):
    """The delivery ledger and queue controls, for staff."""

    permission_classes = [IsAdmin]
    pagination_class = StandardPagination
    serializer_class = NotificationAdminSerializer
    queryset = Notification.objects.none()

    def get_queryset(self) -> Any:
        """Return the ledger, filtered by ``?status=`` and ``?channel=``."""
        queryset = Notification.objects.with_recipient()

        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        channel = self.request.query_params.get("channel")
        if channel:
            queryset = queryset.on_channel(channel)

        return queryset.order_by("-created_at")

    @extend_schema(
        summary="Delivery ledger",
        parameters=[
            OpenApiParameter("status", str, description="pending|sent|failed|delivered"),
            OpenApiParameter("channel", str, description="in_app|email|sms|push"),
        ],
        responses={200: NotificationAdminSerializer(many=True)},
    )
    def list(self, request: Request) -> Response:
        """Return sent and pending notifications."""
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(
            page if page is not None else queryset, many=True
        )
        if page is not None:
            response = self.get_paginated_response(serializer.data)
            response.message = "Notification ledger retrieved."
            return response
        return success_response(serializer.data, message="Notification ledger retrieved.")

    @extend_schema(summary="Delivery statistics", responses={200: NotificationStatsSerializer})
    @action(detail=False, methods=["get"])
    def stats(self, request: Request) -> Response:
        """Return counts by status and channel."""
        return success_response(
            NotificationStatsSerializer(services.get_stats()).data,
            message="Notification statistics retrieved.",
        )

    @extend_schema(summary="Drain the queue now", responses={200: QueueResultSerializer})
    @action(
        detail=False,
        methods=["post"],
        url_path="drain",
        throttle_classes=[NotificationQueueThrottle],
    )
    def drain(self, request: Request) -> Response:
        """Deliver pending notifications without waiting for the worker."""
        return success_response(
            QueueResultSerializer(services.drain_queue()).data,
            message="Notification queue drained.",
        )

    @extend_schema(summary="Retry failed deliveries", responses={200: QueueResultSerializer})
    @action(
        detail=False,
        methods=["post"],
        url_path="retry",
        throttle_classes=[NotificationQueueThrottle],
    )
    def retry(self, request: Request) -> Response:
        """Re-attempt failed deliveries that have attempts left."""
        return success_response(
            QueueResultSerializer(services.retry_failed()).data,
            message="Failed notifications retried.",
        )
