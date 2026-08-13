"""Banner serializers.

Image fields are returned as absolute URLs. DRF's ``ImageField`` does that
automatically when the serializer is given a ``request`` in its context, which
every view here does — a relative ``/media/...`` path forces the Next.js client
to know the API origin and breaks the moment media moves to a CDN.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.banner.models import Banner


class BannerSerializer(serializers.ModelSerializer):
    """A banner as the storefront renders it."""

    id = serializers.UUIDField(source="uuid", read_only=True)
    placement_display = serializers.CharField(
        source="get_placement_display", read_only=True
    )
    # Falls back to the desktop crop, so the client never has to null-check.
    mobile_image = serializers.SerializerMethodField()

    class Meta:
        model = Banner
        fields = (
            "id",
            "title",
            "subtitle",
            "placement",
            "placement_display",
            "image",
            "mobile_image",
            "alt_text",
            "button_text",
            "button_link",
            "display_order",
        )
        read_only_fields = fields

    def get_mobile_image(self, obj: Banner) -> str | None:
        """Return the phone crop, falling back to the desktop image."""
        source = obj.mobile_image or obj.image
        if not source:
            return None
        request = self.context.get("request")
        url = source.url
        return request.build_absolute_uri(url) if request else url


class BannerAdminSerializer(serializers.ModelSerializer):
    """A banner as staff manage it — schedule, counters and all."""

    id = serializers.UUIDField(source="uuid", read_only=True)
    is_live = serializers.BooleanField(read_only=True)
    click_through_rate = serializers.FloatField(read_only=True)

    class Meta:
        model = Banner
        fields = (
            "id",
            "pk",
            "title",
            "subtitle",
            "placement",
            "image",
            "mobile_image",
            "alt_text",
            "button_text",
            "button_link",
            "display_order",
            "is_active",
            "starts_at",
            "ends_at",
            "is_live",
            "impression_count",
            "click_count",
            "click_through_rate",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "pk",
            "is_live",
            "impression_count",
            "click_count",
            "click_through_rate",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Reject a schedule that closes before it opens.

        Checked here as well as by the database CHECK so the admin gets a field
        error rather than an IntegrityError page.
        """
        starts = attrs.get("starts_at") or getattr(self.instance, "starts_at", None)
        ends = attrs.get("ends_at") or getattr(self.instance, "ends_at", None)

        if starts and ends and ends <= starts:
            raise serializers.ValidationError(
                {"ends_at": "The end time must be after the start time."}
            )
        return attrs
