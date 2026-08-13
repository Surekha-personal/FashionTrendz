"""Tests for the notifications module.

Weighted toward the two ways a notification system does damage: sending a
customer something they opted out of, and sending them the same thing five
times because a gateway saved a row five times.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.core import mail
from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalog.models import Brand, Category, SubCategory
from apps.core.choices import OrderStatus
from apps.notifications import services
from apps.notifications.channels import (
    DeliveryError,
    EmailChannel,
    get_channel,
    reset_channel_cache,
)
from apps.notifications.models import (
    Notification,
    NotificationCategory,
    NotificationChannel,
    NotificationPreference,
    NotificationStatus,
)
from apps.notifications.templates import TEMPLATES, get_template
from apps.notifications.validators import validate_event_key, validate_push_token
from apps.orders.models import Order, OrderItem, OrderStatusHistory
from apps.products.models import Product, ProductVariant, Size
from apps.users.models import User

STRONG_PASSWORD = "Tr3ndz!Shopper42"


class BrokenChannel:
    """A channel that always fails, for testing the failure path."""

    name = "broken"

    def is_configured(self) -> bool:
        """Claim to be ready, so the failure happens in ``send``."""
        return True

    def send(self, notification: Any) -> str:
        """Always fail."""
        raise DeliveryError("provider exploded")


class NotificationFixtureMixin:
    """Builds customers and an order to notify about."""

    def build_world(self) -> None:
        """Create the objects the triggers fire on.

        Creating a user fires the welcome trigger, so the outbox and the
        notification tables are cleared *after* the fixture rather than before.
        Otherwise every assertion about "what did this action send?" is really
        an assertion about the fixture.
        """
        reset_channel_cache()
        self._order_seq = 0

        self.user = User.objects.create_user(
            email="shopper@example.com", password=STRONG_PASSWORD, first_name="Aditi"
        )
        self.stranger = User.objects.create_user(
            email="other@example.com", password=STRONG_PASSWORD, first_name="Rhea"
        )
        self.staff = User.objects.create_user(
            email="staff@example.com",
            password=STRONG_PASSWORD,
            first_name="Staff",
            is_staff=True,
        )

        Notification.objects.all().delete()
        NotificationPreference.objects.all().delete()
        mail.outbox = []

    def make_order(self, user: User | None = None, **extra: Any) -> Order:
        """Create an order."""
        self._order_seq += 1
        return Order.objects.create(
            user=user or self.user,
            order_number=f"FT-NOT-{self._order_seq:05d}",
            shipping_address={"city": "Mumbai"},
            billing_address={"city": "Mumbai"},
            subtotal=Decimal("1500.00"),
            grand_total=Decimal("1500.00"),
            **extra,
        )


class NotificationTestCase(NotificationFixtureMixin, TestCase):
    """Base case with the world built."""

    def setUp(self) -> None:
        self.build_world()


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


class TemplateTests(TestCase):
    """The copy catalogue."""

    def test_every_template_declares_at_least_one_channel(self) -> None:
        for key, template in TEMPLATES.items():
            self.assertTrue(template.channels, msg=f"{key} has no channels")

    def test_every_template_declares_a_known_category(self) -> None:
        valid = set(NotificationCategory.values)
        for key, template in TEMPLATES.items():
            self.assertIn(template.category, valid, msg=key)

    def test_every_template_declares_known_channels(self) -> None:
        valid = set(NotificationChannel.values)
        for key, template in TEMPLATES.items():
            for channel in template.channels:
                self.assertIn(channel, valid, msg=f"{key}: {channel}")

    def test_a_missing_context_key_renders_blank_rather_than_raising(self) -> None:
        # A notification with a blank order number is bad copy; an exception in
        # a signal handler takes the surrounding transaction with it.
        rendered = get_template("order_placed").render({"first_name": "Aditi"})
        self.assertIn("Aditi", rendered["body"])

    def test_an_unknown_event_names_the_known_ones(self) -> None:
        with self.assertRaises(KeyError) as caught:
            get_template("no_such_event")
        self.assertIn("order_placed", str(caught.exception))

    def test_password_reset_is_email_only(self) -> None:
        # A reset link in the in-app inbox is only readable by someone already
        # signed in, who does not need it.
        self.assertEqual(get_template("password_reset").channels, (NotificationChannel.EMAIL,))

    def test_sms_copy_is_shorter_than_email_copy(self) -> None:
        template = get_template("order_shipped")
        rendered = template.render({"order_number": "FT-1", "tracking_number": "X1"})
        self.assertLess(len(rendered["sms"]), len(rendered["body"]))


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


class NotifyTests(NotificationTestCase):
    """The single entry point."""

    def test_notify_fans_out_across_the_templates_channels(self) -> None:
        created = services.notify(self.user, "order_placed", {"order_number": "FT-1"})
        channels = {row.channel for row in created}
        self.assertEqual(channels, set(get_template("order_placed").channels))

    def test_an_in_app_row_is_marked_delivered(self) -> None:
        services.notify(self.user, "welcome", {})
        row = Notification.objects.inbox().get()
        self.assertEqual(row.status, NotificationStatus.DELIVERED)

    def test_an_email_row_is_marked_sent_and_actually_sends(self) -> None:
        services.notify(self.user, "welcome", {})
        row = Notification.objects.on_channel(NotificationChannel.EMAIL).get()

        self.assertEqual(row.status, NotificationStatus.SENT)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Aditi", mail.outbox[0].subject)

    def test_the_channels_argument_narrows_the_fan_out(self) -> None:
        created = services.notify(
            self.user, "order_placed", {}, channels=[NotificationChannel.IN_APP]
        )
        self.assertEqual(len(created), 1)

    def test_an_inactive_account_is_never_contacted(self) -> None:
        self.user.is_active = False
        self.assertEqual(services.notify(self.user, "welcome", {}), [])

    def test_an_anonymous_user_is_never_contacted(self) -> None:
        from django.contrib.auth.models import AnonymousUser

        self.assertEqual(services.notify(AnonymousUser(), "welcome", {}), [])

    def test_decimal_context_survives_the_json_field(self) -> None:
        services.notify(
            self.user, "payment_success", {"amount": Decimal("1500.55")}
        )
        row = Notification.objects.inbox().get()
        self.assertEqual(row.context["amount"], "1500.55")

    def test_notify_many_reaches_everyone(self) -> None:
        sent = services.notify_many([self.user, self.stranger], "welcome", {})
        self.assertEqual(sent, 4)  # two channels each


class PreferenceTests(NotificationTestCase):
    """Opt-outs."""

    def test_preferences_are_created_on_first_use(self) -> None:
        self.assertFalse(NotificationPreference.objects.exists())
        services.get_preference(self.user)
        self.assertTrue(NotificationPreference.objects.filter(user=self.user).exists())

    def test_disabling_email_stops_email_but_not_the_inbox(self) -> None:
        services.update_preference(self.user, email_enabled=False)
        created = services.notify(self.user, "welcome", {})

        self.assertEqual({row.channel for row in created}, {NotificationChannel.IN_APP})
        self.assertEqual(len(mail.outbox), 0)

    def test_disabling_marketing_stops_only_marketing(self) -> None:
        services.update_preference(self.user, marketing_enabled=False)

        self.assertEqual(services.notify(self.user, "abandoned_cart", {}), [])
        # A transactional message is not a subscription.
        self.assertTrue(services.notify(self.user, "order_placed", {}))

    def test_the_in_app_inbox_cannot_be_switched_off(self) -> None:
        # It is the account, not a subscription.
        services.update_preference(
            self.user, email_enabled=False, sms_enabled=False, push_enabled=False
        )
        created = services.notify(self.user, "order_placed", {})
        self.assertEqual({row.channel for row in created}, {NotificationChannel.IN_APP})

    def test_force_overrides_an_opt_out(self) -> None:
        services.update_preference(self.user, email_enabled=False)
        created = services.notify(self.user, "password_changed", {}, force=True)
        self.assertTrue(any(row.channel == NotificationChannel.EMAIL for row in created))

    def test_an_unknown_preference_field_is_ignored(self) -> None:
        preference = services.update_preference(
            self.user, email_enabled=False, is_superuser=True
        )
        self.assertFalse(preference.email_enabled)


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------


class DeliveryTests(NotificationTestCase):
    """Channels and the failure path."""

    def test_a_failed_delivery_is_recorded_not_raised(self) -> None:
        with override_settings(
            NOTIFICATION_EMAIL_BACKEND="apps.notifications.tests.BrokenChannel"
        ):
            reset_channel_cache()
            services.notify(self.user, "welcome", {})

        row = Notification.objects.on_channel(NotificationChannel.EMAIL).get()
        self.assertEqual(row.status, NotificationStatus.FAILED)
        self.assertIn("exploded", row.error)
        self.assertEqual(row.attempts, 1)

    def test_email_to_an_address_less_account_fails_cleanly(self) -> None:
        self.user.email = ""
        notification = Notification(
            user=self.user, event="welcome", subject="Hi", body="Hi", pk=1
        )
        with self.assertRaises(DeliveryError):
            EmailChannel().send(notification)

    def test_a_backend_override_is_honoured(self) -> None:
        with override_settings(SMS_BACKEND="apps.notifications.tests.BrokenChannel"):
            reset_channel_cache()
            self.assertIsInstance(get_channel(NotificationChannel.SMS), BrokenChannel)

    def test_an_already_sent_notification_is_not_sent_twice(self) -> None:
        services.notify(self.user, "welcome", {})
        row = Notification.objects.on_channel(NotificationChannel.EMAIL).get()

        self.assertTrue(services.send_notification(row))
        self.assertEqual(len(mail.outbox), 1)

    def test_draining_the_queue_sends_pending_rows(self) -> None:
        Notification.objects.create(
            user=self.user,
            event="welcome",
            channel=NotificationChannel.EMAIL,
            subject="Queued",
            body="Queued",
        )
        result = services.drain_queue()

        self.assertEqual(result["sent"], 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_retry_skips_rows_that_exhausted_their_attempts(self) -> None:
        # An uncapped retry loop turns one dead mailbox into an endless queue.
        Notification.objects.create(
            user=self.user,
            event="welcome",
            channel=NotificationChannel.EMAIL,
            subject="Dead",
            body="Dead",
            status=NotificationStatus.FAILED,
            attempts=services.MAX_DELIVERY_ATTEMPTS,
        )
        self.assertEqual(services.retry_failed()["processed"], 0)

    def test_retry_reattempts_rows_with_attempts_left(self) -> None:
        Notification.objects.create(
            user=self.user,
            event="welcome",
            channel=NotificationChannel.EMAIL,
            subject="Retryable",
            body="Retryable",
            status=NotificationStatus.FAILED,
            attempts=1,
        )
        self.assertEqual(services.retry_failed()["sent"], 1)

    def test_purge_removes_only_stale_rows(self) -> None:
        services.notify(self.user, "welcome", {})
        Notification.objects.update(created_at=timezone.now() - timezone.timedelta(days=400))
        services.notify(self.stranger, "welcome", {})

        self.assertEqual(services.purge_old(180), 2)
        self.assertEqual(Notification.objects.count(), 2)


# ---------------------------------------------------------------------------
# Triggers
# ---------------------------------------------------------------------------


class TriggerTests(NotificationTestCase):
    """The automatic wiring into other modules."""

    def test_registering_sends_a_welcome(self) -> None:
        User.objects.create_user(
            email="new@example.com", password=STRONG_PASSWORD, first_name="New"
        )
        self.assertTrue(
            Notification.objects.filter(
                user__email="new@example.com", event="welcome"
            ).exists()
        )

    def test_a_staff_account_gets_no_welcome(self) -> None:
        User.objects.create_user(
            email="admin2@example.com",
            password=STRONG_PASSWORD,
            first_name="Admin",
            is_staff=True,
        )
        self.assertFalse(
            Notification.objects.filter(user__email="admin2@example.com").exists()
        )

    def test_placing_an_order_notifies_the_customer(self) -> None:
        order = self.make_order()
        self.assertTrue(
            Notification.objects.filter(
                event="order_placed", subject__contains=order.order_number
            ).exists()
        )

    def test_a_status_history_row_announces_the_transition(self) -> None:
        order = self.make_order()
        OrderStatusHistory.objects.create(
            order=order, previous_status=OrderStatus.PACKED, status=OrderStatus.SHIPPED
        )
        self.assertTrue(
            Notification.objects.filter(event="order_shipped").exists()
        )

    def test_an_internal_transition_is_not_announced(self) -> None:
        # PROCESSING is warehouse vocabulary, not news.
        order = self.make_order()
        OrderStatusHistory.objects.create(
            order=order, status=OrderStatus.PROCESSING
        )
        self.assertFalse(Notification.objects.filter(event="order_packed").exists())

    def test_saving_an_order_again_does_not_re_announce_it(self) -> None:
        # The classic bug: post_save on Order fires for every field change.
        order = self.make_order()
        before = Notification.objects.filter(event="order_placed").count()

        order.internal_notes = "checked by warehouse"
        order.save(update_fields=["internal_notes"])

        self.assertEqual(
            Notification.objects.filter(event="order_placed").count(), before
        )

    def test_a_repeated_payment_save_notifies_once(self) -> None:
        from apps.payments.models import Payment, PaymentState

        order = self.make_order()
        payment = Payment.objects.create(
            order=order,
            gateway="razorpay",
            amount=Decimal("1500.00"),
            status=PaymentState.CAPTURED,
        )
        payment.save()
        payment.save()

        self.assertEqual(
            Notification.objects.filter(
                event="payment_success", channel=NotificationChannel.IN_APP
            ).count(),
            1,
        )

    def test_a_failed_payment_notifies_with_a_reason(self) -> None:
        from apps.payments.models import Payment, PaymentState

        order = self.make_order()
        Payment.objects.create(
            order=order,
            gateway="razorpay",
            amount=Decimal("1500.00"),
            status=PaymentState.FAILED,
            failure_reason="Insufficient funds.",
        )
        row = Notification.objects.filter(
            event="payment_failed", channel=NotificationChannel.IN_APP
        ).first()

        self.assertIsNotNone(row)
        self.assertIn("Insufficient funds.", row.body)


# ---------------------------------------------------------------------------
# Inbox
# ---------------------------------------------------------------------------


class InboxTests(NotificationTestCase):
    """Reading and clearing the bell menu."""

    def setUp(self) -> None:
        super().setUp()
        services.notify(self.user, "welcome", {})

    def test_the_inbox_excludes_the_delivery_ledger(self) -> None:
        # Email rows share the table; showing them would double every event.
        self.assertEqual(services.get_inbox(self.user).count(), 1)

    def test_unread_count_counts_only_in_app_rows(self) -> None:
        self.assertEqual(services.unread_count(self.user), 1)

    def test_marking_read_clears_the_badge(self) -> None:
        row = services.get_inbox(self.user).first()
        self.assertTrue(services.mark_read(self.user, str(row.uuid)))
        self.assertEqual(services.unread_count(self.user), 0)

    def test_one_customer_cannot_mark_anothers_notification_read(self) -> None:
        row = services.get_inbox(self.user).first()
        self.assertFalse(services.mark_read(self.stranger, str(row.uuid)))

    def test_mark_all_read_is_one_update(self) -> None:
        services.notify(self.user, "order_placed", {})
        self.assertEqual(services.mark_all_read(self.user), 2)
        self.assertEqual(services.unread_count(self.user), 0)


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


class ValidatorTests(TestCase):
    """Boundary checks."""

    def test_a_normal_push_token_is_accepted(self) -> None:
        validate_push_token("fLx3_aB-9:APA91bH.tokenvalue")

    def test_a_token_with_spaces_is_rejected(self) -> None:
        with self.assertRaises(DjangoValidationError):
            validate_push_token("not a token")

    def test_an_overlong_token_is_rejected(self) -> None:
        with self.assertRaises(DjangoValidationError):
            validate_push_token("a" * 300)

    def test_a_blank_token_is_allowed(self) -> None:
        # Clearing a device registration is a legitimate update.
        validate_push_token("")

    def test_a_known_event_key_passes(self) -> None:
        validate_event_key("order_placed")

    def test_an_unknown_event_key_is_rejected(self) -> None:
        with self.assertRaises(DjangoValidationError):
            validate_event_key("order_teleported")


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


class NotificationAPITests(NotificationFixtureMixin, APITestCase):
    """The HTTP surface."""

    def setUp(self) -> None:
        self.build_world()
        services.notify(self.user, "welcome", {})

    def test_the_inbox_requires_authentication(self) -> None:
        response = self.client.get(reverse("notifications:notification-list"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_a_customer_sees_only_their_own_inbox(self) -> None:
        self.client.force_authenticate(user=self.stranger)
        response = self.client.get(reverse("notifications:notification-list"))
        self.assertEqual(len(response.json()["data"]), 0)

    def test_the_inbox_lists_in_app_notifications(self) -> None:
        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse("notifications:notification-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()["data"]), 1)

    def test_the_unread_count_endpoint(self) -> None:
        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse("notifications:notification-unread-count"))
        self.assertEqual(response.json()["data"]["unread"], 1)

    def test_marking_all_read(self) -> None:
        self.client.force_authenticate(user=self.user)
        response = self.client.post(reverse("notifications:notification-read-all"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(services.unread_count(self.user), 0)

    def test_reading_and_updating_preferences(self) -> None:
        self.client.force_authenticate(user=self.user)
        url = reverse("notifications:notification-preferences")

        self.assertTrue(self.client.get(url).json()["data"]["email_enabled"])

        response = self.client.patch(url, {"email_enabled": False}, format="json")
        self.assertFalse(response.json()["data"]["email_enabled"])

    def test_the_push_token_is_never_echoed_back(self) -> None:
        self.client.force_authenticate(user=self.user)
        url = reverse("notifications:notification-preferences")

        response = self.client.patch(url, {"push_token": "abc123"}, format="json")
        self.assertNotIn("push_token", response.json()["data"])
        self.assertTrue(response.json()["data"]["has_push_token"])

    def test_the_admin_ledger_is_staff_only(self) -> None:
        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse("notifications:notification-admin-list"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_see_every_channel_in_the_ledger(self) -> None:
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(reverse("notifications:notification-admin-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.json()["data"]), 2)

    def test_staff_can_read_delivery_statistics(self) -> None:
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(reverse("notifications:notification-admin-stats"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("by_channel", response.json()["data"])
