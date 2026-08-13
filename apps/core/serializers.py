"""Core serializers.

Only the monitoring response shapes. Everything else the core app provides is
infrastructure — renderers, pagination, permissions — that other modules'
serializers build on.
"""

from __future__ import annotations

from rest_framework import serializers


class HealthCheckSerializer(serializers.Serializer):
    """The result of one dependency check."""

    name = serializers.CharField(read_only=True)
    ok = serializers.BooleanField(read_only=True)
    detail = serializers.CharField(read_only=True, allow_blank=True)
    duration_ms = serializers.FloatField(read_only=True)


class HealthReportSerializer(serializers.Serializer):
    """The health endpoint's payload.

    Not wrapped in the project envelope. Load balancers and uptime monitors
    parse this with a fixed JSON path, and they should not have to know about
    ``{success, message, data}`` to read a boolean.
    """

    status = serializers.CharField(read_only=True)
    healthy = serializers.BooleanField(read_only=True)
    checked_at = serializers.DateTimeField(read_only=True)
    failed = serializers.ListField(child=serializers.CharField(), read_only=True)
    checks = HealthCheckSerializer(many=True, read_only=True)


class ApplicationStatusSerializer(serializers.Serializer):
    """Build and configuration information."""

    name = serializers.CharField(read_only=True)
    version = serializers.CharField(read_only=True)
    environment = serializers.CharField(read_only=True)
    debug = serializers.BooleanField(read_only=True)
    time = serializers.DateTimeField(read_only=True)
    timezone = serializers.CharField(read_only=True)
    database = serializers.CharField(read_only=True)
    cache = serializers.CharField(read_only=True)
    celery_configured = serializers.BooleanField(read_only=True)
    email_configured = serializers.BooleanField(read_only=True)
    storage = serializers.CharField(read_only=True)
    installed_apps = serializers.IntegerField(read_only=True)


class SystemInformationSerializer(serializers.Serializer):
    """Interpreter, framework and host details."""

    python = serializers.CharField(read_only=True)
    django = serializers.CharField(read_only=True)
    platform = serializers.CharField(read_only=True)
    processor = serializers.CharField(read_only=True)
    hostname = serializers.CharField(read_only=True)
    pid = serializers.IntegerField(read_only=True)
    cpu_count = serializers.IntegerField(read_only=True, allow_null=True)
