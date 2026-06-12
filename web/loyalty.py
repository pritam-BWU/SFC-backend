from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import LoyaltyRewardLedger, RewardLedger, RewardPoints, SubscriptionStatusMaster, UserLoyaltyAccount, UserProfile
from .notifications import create_notification_for_event
from .reward_engine import credit_reward_ledger


LOCK_DAYS = 365


def get_loyalty_account(profile):
    account, _ = UserLoyaltyAccount.objects.get_or_create(user_profile=profile)
    return account


def get_reward_points(profile):
    points, _ = RewardPoints.objects.get_or_create(user_profile=profile)
    if profile.points_id != points.id:
        profile.points = points
        profile.save(update_fields=['points', 'updated_at'])
    return points


def is_loyalty_eligible(profile):
    return bool(
        profile.is_active
        and profile.subscription_plan_id
        and profile.subscription_status
        and profile.subscription_status.status_name == 'completed'
    )


def can_change_loyalty_preference(profile, today=None):
    today = today or timezone.localdate()
    return not profile.loyalty_preference_locked_until or profile.loyalty_preference_locked_until <= today


def get_preference_label(preference):
    choices = dict(UserProfile.LoyaltyRewardPreference.choices)
    return choices.get(preference, '')


def select_loyalty_preference(profile, preference):
    if preference not in UserProfile.LoyaltyRewardPreference.values:
        raise ValueError('Invalid loyalty reward preference.')

    if not is_loyalty_eligible(profile):
        raise ValueError('Loyalty preference can be selected only after membership approval.')

    if (
        profile.loyalty_reward_preference is not None
        and profile.loyalty_reward_preference != preference
        and not can_change_loyalty_preference(profile)
    ):
        raise ValueError('Loyalty preference is locked for one year from the selected date.')

    now = timezone.now()
    profile.loyalty_reward_preference = preference
    profile.loyalty_preference_selected_at = now
    profile.loyalty_preference_locked_until = timezone.localdate() + timedelta(days=LOCK_DAYS)
    profile.save(
        update_fields=[
            'loyalty_reward_preference',
            'loyalty_preference_selected_at',
            'loyalty_preference_locked_until',
            'updated_at',
        ]
    )
    get_loyalty_account(profile)
    get_reward_points(profile)
    create_notification_for_event(
        profile,
        'loyalty_preference_selected',
        context={
            'reward_frequency': get_preference_label(preference),
            'locked_until': profile.loyalty_preference_locked_until.strftime('%d %b %Y'),
        },
        dedupe_key=f'{profile.id}:loyalty_preference_selected:{now.date().isoformat()}',
    )
    return profile


def get_reward_amount(profile):
    if profile.loyalty_reward_preference == UserProfile.LoyaltyRewardPreference.MONTHLY:
        return profile.subscription_plan.monthly_reward
    if profile.loyalty_reward_preference == UserProfile.LoyaltyRewardPreference.YEARLY:
        return profile.subscription_plan.yearly_reward
    return Decimal('0.00')


def get_reward_period_key(preference, reward_date=None):
    reward_date = reward_date or timezone.localdate()
    if preference == UserProfile.LoyaltyRewardPreference.YEARLY:
        return reward_date.strftime('%Y')
    return reward_date.strftime('%Y-%m')


def credit_loyalty_reward(profile, source=LoyaltyRewardLedger.SourceChoices.SYSTEM, reward_date=None, reference_id='', note=''):
    if not is_loyalty_eligible(profile):
        raise ValueError('User is not eligible for loyalty rewards yet.')

    if profile.loyalty_reward_preference is None:
        raise ValueError('User has not selected monthly or yearly loyalty reward preference.')

    amount = get_reward_amount(profile)
    if amount <= 0:
        raise ValueError('Selected subscription plan has no reward amount configured.')

    period_key = get_reward_period_key(profile.loyalty_reward_preference, reward_date)

    with transaction.atomic():
        account, _ = UserLoyaltyAccount.objects.select_for_update().get_or_create(user_profile=profile)
        points, _ = RewardPoints.objects.select_for_update().get_or_create(user_profile=profile)
        if profile.points_id != points.id:
            profile.points = points
            profile.save(update_fields=['points', 'updated_at'])

        existing_entry = LoyaltyRewardLedger.objects.filter(
            user_profile=profile,
            reward_preference=profile.loyalty_reward_preference,
            period_key=period_key,
            entry_type=LoyaltyRewardLedger.EntryType.CREDIT,
        ).first()
        if existing_entry:
            return existing_entry, False

        new_balance = account.balance + amount
        new_loyalty_reward = points.loyalty_reward + amount
        entry = LoyaltyRewardLedger.objects.create(
            user_profile=profile,
            account=account,
            subscription_plan=profile.subscription_plan,
            entry_type=LoyaltyRewardLedger.EntryType.CREDIT,
            reward_preference=profile.loyalty_reward_preference,
            amount=amount,
            balance_after=new_loyalty_reward,
            period_key=period_key,
            reference_id=reference_id,
            source=source,
            note=note,
        )
        points.loyalty_reward = new_loyalty_reward
        points.save(update_fields=['loyalty_reward', 'updated_at'])
        account.balance = new_balance
        account.lifetime_earned += amount
        now = timezone.now()
        if profile.loyalty_reward_preference == UserProfile.LoyaltyRewardPreference.MONTHLY:
            account.last_monthly_credit_at = now
            update_fields = ['balance', 'lifetime_earned', 'last_monthly_credit_at', 'updated_at']
        else:
            account.last_yearly_credit_at = now
            update_fields = ['balance', 'lifetime_earned', 'last_yearly_credit_at', 'updated_at']
        account.save(update_fields=update_fields)

    create_notification_for_event(
        profile,
        'loyalty_reward_credited',
        context={
            'reward_amount': str(amount),
            'reward_frequency': get_preference_label(profile.loyalty_reward_preference),
            'reward_period': period_key,
            'loyalty_balance': str(entry.balance_after),
        },
        dedupe_key=f'{profile.id}:loyalty_reward_credited:{entry.id}',
    )
    credit_reward_ledger(
        profile=profile,
        reward_type=RewardLedger.RewardType.LOYALTY,
        amount=amount,
        subscription_plan=profile.subscription_plan,
        reward_subtype=get_preference_label(profile.loyalty_reward_preference),
        base_amount=amount,
        calculated_amount=amount,
        reference_id=reference_id or f'loyalty:{entry.id}',
        note=note or f'Loyalty reward credited for {period_key}.',
        idempotency_key=f'loyalty:{profile.id}:{profile.loyalty_reward_preference}:{period_key}',
    )
    return entry, True


def credit_due_loyalty_rewards(source=LoyaltyRewardLedger.SourceChoices.SYSTEM, reward_date=None, note=''):
    completed_status = SubscriptionStatusMaster.objects.filter(status_name='completed').first()
    if not completed_status:
        return {'credited': 0, 'skipped': 0, 'errors': []}

    profiles = UserProfile.objects.select_related('subscription_plan', 'subscription_status').filter(
        is_active=True,
        subscription_status=completed_status,
        subscription_plan__isnull=False,
        loyalty_reward_preference__isnull=False,
    )

    result = {'credited': 0, 'skipped': 0, 'errors': []}
    for profile in profiles.iterator():
        try:
            _, created = credit_loyalty_reward(
                profile,
                source=source,
                reward_date=reward_date,
                note=note,
            )
            if created:
                result['credited'] += 1
            else:
                result['skipped'] += 1
        except ValueError as error:
            result['skipped'] += 1
            result['errors'].append(f'{profile.id}: {error}')
    return result
