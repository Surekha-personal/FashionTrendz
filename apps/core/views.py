"""Monitoring endpoints.

The only views in the core app. Everything else here is infrastructure other
modules import.

``/health/`` is public and shallow — it is polled by a load balancer, which has
no credentials and must not be able to enumerate the deployment. The detailed
variants are staff-only, because "which dependencies exist and which are
broken" is reconnaissance.
"""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import health
from apps.core.permissions import IsAdmin
from apps.core.responses import success_response
from apps.core.serializers import (
    ApplicationStatusSerializer,
    HealthReportSerializer,
    SystemInformationSerializer,
)


@extend_schema(tags=["Monitoring"])
class HealthCheckAPIView(APIView):
    """Liveness and readiness probe.

    Public and unthrottled. A load balancer polling every two seconds would
    exhaust any sane rate limit, and a health endpoint that starts returning
    429 takes the whole service out of rotation.

    Returns 503 when a critical dependency is down, so orchestrators can act on
    the status code without parsing the body.
    """

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_classes: list[Any] = []
    # Plain JSON, not the project envelope. Uptime monitors and orchestrators
    # parse a fixed path such as `.healthy`, and they should not have to learn
    # `{success, message, data}` to read one boolean.
    renderer_classes = [JSONRenderer]

    @extend_schema(
        summary="Health check",
        parameters=[
            OpenApiParameter(
                "deep",
                bool,
                description="Also check storage, email and Celery. Staff only.",
            )
        ],
        responses={200: HealthReportSerializer, 503: HealthReportSerializer},
    )
    def get(self, request: Request) -> Response:
        """Return the health report."""
        user = getattr(request, "user", None)
        wants_deep = str(request.query_params.get("deep", "")).lower() in {
            "1",
            "true",
            "yes",
        }
        # Deep checks open SMTP and storage connections. Anonymous callers get
        # the shallow version however they ask.
        deep = wants_deep and bool(user and user.is_authenticated and user.is_staff)

        report = health.run_checks(deep=deep)
        return Response(
            report,
            status=(
                status.HTTP_200_OK
                if report["healthy"]
                else status.HTTP_503_SERVICE_UNAVAILABLE
            ),
        )


@extend_schema(tags=["Monitoring"])
class ReadinessAPIView(APIView):
    """Kubernetes-style readiness probe.

    Separate from ``/health/`` because the two answer different questions.
    Liveness asks "should this container be restarted?"; readiness asks "should
    traffic be sent to it?" A pod with a cold cache is alive but not ready, and
    conflating them causes restart loops during a deploy.
    """

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_classes: list[Any] = []
    # Plain JSON, not the project envelope. Uptime monitors and orchestrators
    # parse a fixed path such as `.healthy`, and they should not have to learn
    # `{success, message, data}` to read one boolean.
    renderer_classes = [JSONRenderer]

    @extend_schema(summary="Readiness probe", responses={200: None, 503: None})
    def get(self, request: Request) -> Response:
        """Return 200 when this instance can serve traffic."""
        report = health.run_checks(deep=False)
        return Response(
            {"ready": report["healthy"], "failed": report["failed"]},
            status=(
                status.HTTP_200_OK
                if report["healthy"]
                else status.HTTP_503_SERVICE_UNAVAILABLE
            ),
        )


@extend_schema(tags=["Monitoring"])
class ApplicationStatusAPIView(APIView):
    """What this build is and how it is configured. Staff only."""

    permission_classes = [IsAdmin]

    @extend_schema(
        summary="Application status", responses={200: ApplicationStatusSerializer}
    )
    def get(self, request: Request) -> Response:
        """Return build and configuration information."""
        return success_response(
            health.application_status(), message="Application status retrieved."
        )


@extend_schema(tags=["Monitoring"])
class SystemInformationAPIView(APIView):
    """Runtime and platform information. Staff only."""

    permission_classes = [IsAdmin]

    @extend_schema(
        summary="System information", responses={200: SystemInformationSerializer}
    )
    def get(self, request: Request) -> Response:
        """Return interpreter, framework and host details."""
        return success_response(
            health.system_information(), message="System information retrieved."
        )
