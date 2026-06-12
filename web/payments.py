import hashlib
import hmac
import json

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import (
    PaymentOrder,
    PaymentProvider,
    PaymentRefund,
    PaymentTransaction,
    PaymentWebhookEvent,
    SubscriptionStatusMaster,
)
from .notifications import create_notification_for_event


def get_razorpay_provider():
    provider, _ = PaymentProvider.objects.get_or_create(
        provider_key='razorpay',
        defaults={
            'provider_name': 'Razorpay',
            'mode': PaymentProvider.ModeChoices.TEST,
            'is_active': True,
        },
    )
    return provider


def create_payment_order(profile, subscription_plan, amount=None, notes=None):
    provider = get_razorpay_provider()
    payable_amount = amount if amount is not None else subscription_plan.plan_price
    order = PaymentOrder.objects.create(
        user_profile=profile,
        subscription_plan=subscription_plan,
        provider=provider,
        amount=payable_amount,
        currency=getattr(settings, 'PAYMENT_DEFAULT_CURRENCY', 'INR'),
        status=PaymentOrder.StatusChoices.CREATED,
        notes=notes or {},
    )
    return order


def verify_razorpay_payment_signature(gateway_order_id, gateway_payment_id, signature):
    secret = getattr(settings, 'RAZORPAY_KEY_SECRET', '')
    if not secret:
        return not getattr(settings, 'RAZORPAY_REQUIRE_SIGNATURE', False)

    payload = f'{gateway_order_id}|{gateway_payment_id}'.encode()
    expected_signature = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected_signature, signature or '')


def verify_razorpay_webhook_signature(raw_body, signature):
    secret = getattr(settings, 'RAZORPAY_WEBHOOK_SECRET', '')
    if not secret:
        return not getattr(settings, 'RAZORPAY_REQUIRE_SIGNATURE', False)

    expected_signature = hmac.new(
        secret.encode(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected_signature, signature or '')


@transaction.atomic
def confirm_payment(order, gateway_payment_id, gateway_signature='', raw_payload=None):
    gateway_order_id = order.gateway_order_id or order.receipt
    signature_valid = verify_razorpay_payment_signature(
        gateway_order_id,
        gateway_payment_id,
        gateway_signature,
    )
    if not signature_valid:
        raise ValueError('Invalid Razorpay payment signature.')

    now = timezone.now()
    transaction_obj, _ = PaymentTransaction.objects.update_or_create(
        gateway_payment_id=gateway_payment_id,
        defaults={
            'payment_order': order,
            'user_profile': order.user_profile,
            'provider': order.provider,
            'gateway_signature': gateway_signature,
            'amount': order.amount,
            'currency': order.currency,
            'status': PaymentTransaction.StatusChoices.CAPTURED,
            'gateway_status': 'captured',
            'raw_payload': raw_payload or {},
            'paid_at': now,
        },
    )

    order.status = PaymentOrder.StatusChoices.PAID
    order.paid_at = now
    order.save(update_fields=['status', 'paid_at', 'updated_at'])

    pending_status = SubscriptionStatusMaster.objects.filter(status_name='pending').first()
    profile = order.user_profile
    profile.subscription_plan = order.subscription_plan
    profile.subscription_status = pending_status
    profile.payment_details = (
        f'Amount: Rs. {order.amount}; Method: Razorpay; '
        f'Payment ID: {gateway_payment_id}; Order: {gateway_order_id}'
    )
    profile.save(update_fields=['subscription_plan', 'subscription_status', 'payment_details', 'updated_at'])

    create_notification_for_event(profile, 'payment_completed')
    create_notification_for_event(profile, 'subscription_pending_review')
    return transaction_obj


@transaction.atomic
def request_refund(order, amount=None, reason='', requested_by=None):
    provider = order.provider
    transaction_obj = order.transactions.filter(
        status=PaymentTransaction.StatusChoices.CAPTURED,
    ).order_by('-paid_at', '-created_at').first()
    refund = PaymentRefund.objects.create(
        payment_order=order,
        payment_transaction=transaction_obj,
        user_profile=order.user_profile,
        provider=provider,
        amount=amount or order.amount,
        currency=order.currency,
        reason=reason,
        requested_by=requested_by,
        status=PaymentRefund.StatusChoices.REQUESTED,
    )
    order.status = PaymentOrder.StatusChoices.REFUNDED
    order.save(update_fields=['status', 'updated_at'])
    return refund


def store_webhook_event(provider, raw_body, headers):
    signature = headers.get('X-Razorpay-Signature', '')
    is_valid = verify_razorpay_webhook_signature(raw_body, signature)

    try:
        payload = json.loads(raw_body.decode() if isinstance(raw_body, bytes) else raw_body)
    except json.JSONDecodeError:
        payload = {}

    event_id = payload.get('id') or payload.get('payload', {}).get('payment', {}).get('entity', {}).get('id')
    webhook_event = PaymentWebhookEvent.objects.create(
        provider=provider,
        event_id=event_id,
        event_name=payload.get('event', 'unknown'),
        signature=signature,
        payload=payload,
        headers={key: value for key, value in headers.items()},
        is_valid_signature=is_valid,
    )
    return webhook_event
