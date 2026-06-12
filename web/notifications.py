from collections import defaultdict

from django.db import transaction

from .models import NotificationEventMaster, NotificationRule, UserNotification


class SafeTemplateContext(defaultdict):
    def __missing__(self, key):
        return ''


def build_notification_context(profile, extra_context=None):
    plan = profile.subscription_plan
    status = profile.subscription_status
    context = {
        'full_name': profile.full_name,
        'member_id': profile.id,
        'username': profile.user.username,
        'phone_number': profile.phone_number,
        'email_address': profile.email_address or profile.user.email,
        'plan_name': plan.plan_name if plan else '',
        'plan_price': str(plan.plan_price) if plan else '',
        'subscription_status': status.status_name if status else '',
        'city': profile.city,
        'created_date': profile.created_at.strftime('%d %b %Y') if profile.created_at else '',
        'reward_frequency': profile.get_loyalty_reward_preference_display() if profile.loyalty_reward_preference is not None else '',
        'locked_until': profile.loyalty_preference_locked_until.strftime('%d %b %Y') if profile.loyalty_preference_locked_until else '',
        'reward_amount': '',
        'reward_period': '',
        'loyalty_balance': '',
        'reward_percentage': '',
        'referral_count': '',
        'referral_level': '',
        'referral_role': '',
        'global_pool_balance': '',
        'global_pool_limit': '',
    }

    if extra_context:
        context.update(extra_context)

    return context


def render_template(template, context):
    try:
        return template.format_map(SafeTemplateContext(str, context))
    except ValueError:
        return template


def create_notification_for_event(profile, event_key, context=None, dedupe_key=None):
    if not profile:
        return None

    try:
        event = NotificationEventMaster.objects.get(event_key=event_key, is_active=True)
        rule = NotificationRule.objects.get(
            event=event,
            is_active=True,
            send_immediately=True,
        )
    except (NotificationEventMaster.DoesNotExist, NotificationRule.DoesNotExist):
        return None

    template_context = build_notification_context(profile, context)
    title = render_template(rule.title_template, template_context)
    message = render_template(rule.message_template, template_context)
    resolved_dedupe_key = dedupe_key or f'{profile.id}:{event_key}'

    def create_notification():
        notification, _ = UserNotification.objects.get_or_create(
            dedupe_key=resolved_dedupe_key,
            defaults={
                'user_profile': profile,
                'event': event,
                'created_by_rule': rule,
                'title': title,
                'message': message,
                'deep_link': rule.deep_link,
                'metadata': template_context,
            },
        )
        return notification

    transaction.on_commit(create_notification)
    return True
