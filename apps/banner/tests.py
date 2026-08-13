"""Tests for the banner module."""

from __future__ import annotations

from django.core.management import call_command
from django.db.utils import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.banner.models import Banner, BannerPlacement
from apps.core.seeding import make_banner_image
from apps.users.models import User

STRONG_PASSWORD = "Tr3ndz!Shopper42"


class BannerFixtureMixin:
    """Builds banners across placements and schedule states."""

    def build_world(self) -> None:
        """Create staff, a customer and one live banner."""
        self.staff = User.objects.create_user(
            email="merch@example.com",
            password=STRONG_PASSWORD,
            first_name="Merch",
            is_staff=True,
        )
        self.user = User.objects.create_user(
            email="shopper@example.com", password=STRONG_PASSWORD, first_name="Aditi"
        )
        self.live = self.make_banner("Festive Edit")

    def make_banner(self, title: str, **extra: object) -> Banner:
        """Create a banner, live by default."""
        now = timezone.now()
        defaults: dict[str, object] = {
            "title": title,
            "placement": BannerPlacement.HERO,
            "image": make_banner_image(title),
            "starts_at": now - timezone.timedelta(days=1),
            "is_active": True,
        }
        defaults.update(extra)
        return Banner.objects.create(**defaults)


class BannerModelTests(BannerFixtureMixin, TestCase):
    """Scheduling and derived state."""

    def setUp(self) -> None:
        self.build_world()

    def test_a_banner_inside_its_window_is_live(self) -> None:
        self.assertTrue(self.live.is_live)
        self.assertIn(self.live, Banner.objects.live())

    def test_an_inactive_banner_is_not_live(self) -> None:
        banner = self.make_banner("Switched off", is_active=False)
        self.assertFalse(banner.is_live)
        self.assertNotIn(banner, Banner.objects.live())

    def test_a_future_banner_is_not_live_yet(self) -> None:
        # The whole point of scheduling: nobody should be awake at midnight to
        # tick a box.
        banner = self.make_banner(
            "Tomorrow", starts_at=timezone.now() + timezone.timedelta(days=1)
        )
        self.assertFalse(banner.is_live)
        self.assertIn(banner, Banner.objects.scheduled())

    def test_an_expired_banner_is_not_live(self) -> None:
        banner = self.make_banner(
            "Yesterday",
            starts_at=timezone.now() - timezone.timedelta(days=10),
            ends_at=timezone.now() - timezone.timedelta(days=1),
        )
        self.assertFalse(banner.is_live)
        self.assertIn(banner, Banner.objects.expired())

    def test_an_open_ended_banner_runs_indefinitely(self) -> None:
        self.assertIsNone(self.live.ends_at)
        self.assertTrue(self.live.is_live)

    def test_the_database_refuses_a_backwards_window(self) -> None:
        now = timezone.now()
        with self.assertRaises(IntegrityError):
            Banner.objects.create(
                title="Impossible",
                image=make_banner_image("Impossible"),
                starts_at=now,
                ends_at=now - timezone.timedelta(hours=1),
            )

    def test_click_through_rate_of_zero_impressions_is_zero(self) -> None:
        # Dividing by an unseen banner's impressions would break the admin
        # column rather than report anything useful.
        self.assertEqual(self.live.click_through_rate, 0.0)

    def test_click_through_rate(self) -> None:
        Banner.objects.filter(pk=self.live.pk).update(
            impression_count=200, click_count=15
        )
        self.live.refresh_from_db()
        self.assertEqual(self.live.click_through_rate, 7.5)

    def test_placement_filtering(self) -> None:
        self.make_banner("Strip", placement=BannerPlacement.STRIP)
        self.assertEqual(
            Banner.objects.live().for_placement(BannerPlacement.STRIP).count(), 1
        )


class BannerAPITests(BannerFixtureMixin, APITestCase):
    """The HTTP surface."""

    def setUp(self) -> None:
        self.build_world()

    def test_the_banner_feed_is_public(self) -> None:
        # A storefront homepage renders before anyone signs in.
        response = self.client.get(reverse("banner:banner-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()["data"]), 1)

    def test_the_feed_hides_banners_outside_their_window(self) -> None:
        self.make_banner(
            "Future", starts_at=timezone.now() + timezone.timedelta(days=2)
        )
        response = self.client.get(reverse("banner:banner-list"))
        self.assertEqual(len(response.json()["data"]), 1)

    def test_the_feed_filters_by_placement(self) -> None:
        self.make_banner("Strip", placement=BannerPlacement.STRIP)
        response = self.client.get(
            reverse("banner:banner-list"), {"placement": "strip"}
        )
        self.assertEqual(len(response.json()["data"]), 1)
        self.assertEqual(response.json()["data"][0]["placement"], "strip")

    def test_images_are_returned_as_absolute_urls(self) -> None:
        # A relative /media/ path forces the client to know the API origin and
        # breaks the moment media moves to a CDN.
        data = self.client.get(reverse("banner:banner-list")).json()["data"][0]
        self.assertTrue(data["image"].startswith("http"))
        self.assertTrue(data["mobile_image"].startswith("http"))

    def test_mobile_image_falls_back_to_the_desktop_crop(self) -> None:
        data = self.client.get(reverse("banner:banner-list")).json()["data"][0]
        self.assertEqual(data["mobile_image"], data["image"])

    def test_the_homepage_endpoint_groups_by_placement(self) -> None:
        self.make_banner("Strip", placement=BannerPlacement.STRIP)
        data = self.client.get(reverse("banner:banner-homepage")).json()["data"]

        self.assertEqual(len(data["hero"]), 1)
        self.assertEqual(len(data["strip"]), 1)
        self.assertEqual(data["footer"], [])

    def test_recording_an_impression(self) -> None:
        response = self.client.post(
            reverse("banner:banner-impression", kwargs={"uuid": self.live.uuid})
        )
        self.live.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.live.impression_count, 1)

    def test_recording_a_click(self) -> None:
        self.client.post(reverse("banner:banner-click", kwargs={"uuid": self.live.uuid}))
        self.live.refresh_from_db()
        self.assertEqual(self.live.click_count, 1)

    def test_the_admin_surface_is_staff_only(self) -> None:
        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse("banner:banner-admin-list"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_see_banners_outside_their_window(self) -> None:
        self.make_banner("Future", starts_at=timezone.now() + timezone.timedelta(days=2))
        self.client.force_authenticate(user=self.staff)

        response = self.client.get(reverse("banner:banner-admin-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()["data"]), 2)

    def test_staff_can_create_a_banner(self) -> None:
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(
            reverse("banner:banner-admin-list"),
            {
                "title": "Created via API",
                "placement": "strip",
                "image": make_banner_image("api"),
                "starts_at": timezone.now().isoformat(),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Banner.objects.filter(title="Created via API").exists())

    def test_a_backwards_window_is_a_400_not_a_500(self) -> None:
        self.client.force_authenticate(user=self.staff)
        now = timezone.now()
        response = self.client.patch(
            reverse("banner:banner-admin-detail", kwargs={"uuid": self.live.uuid}),
            {
                "starts_at": now.isoformat(),
                "ends_at": (now - timezone.timedelta(hours=1)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_the_placements_endpoint_reports_live_counts(self) -> None:
        self.client.force_authenticate(user=self.staff)
        data = self.client.get(reverse("banner:banner-admin-placements")).json()["data"]

        hero = next(row for row in data if row["value"] == "hero")
        self.assertEqual(hero["live"], 1)


class BannerSeedTests(TestCase):
    """The seed command."""

    def test_seeding_creates_banners_for_every_placement(self) -> None:
        call_command("seed_banners", verbosity=0)

        self.assertGreaterEqual(Banner.objects.count(), 8)
        for placement in BannerPlacement.values:
            self.assertTrue(
                Banner.objects.for_placement(placement).exists(), msg=placement
            )

    def test_every_seeded_banner_is_live(self) -> None:
        call_command("seed_banners", verbosity=0)
        self.assertEqual(Banner.objects.count(), Banner.objects.live().count())

    def test_seeding_twice_does_not_duplicate(self) -> None:
        call_command("seed_banners", verbosity=0)
        first = Banner.objects.count()
        call_command("seed_banners", verbosity=0)
        self.assertEqual(Banner.objects.count(), first)

    def test_seeded_banners_carry_both_crops(self) -> None:
        call_command("seed_banners", verbosity=0)
        banner = Banner.objects.first()
        self.assertTrue(banner.image)
        self.assertTrue(banner.mobile_image)
