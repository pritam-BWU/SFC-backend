from decimal import Decimal, ROUND_DOWN

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import (
    GlobalPoolDistribution,
    GlobalPoolEvent,
    GlobalPoolMember,
    GlobalPoolSetting,
    PaymentOrder,
    ReferralClosure,
    ReferralEdge,
    RewardLedger,
    RewardPoints,
    RewardRule,
    SubscriptionStatusMaster,
    UserProfile,
)
from .notifications import create_notification_for_event


MONEY_PLACES = Decimal('0.01')
DIRECT_REFERRAL_TO_POOL_COUNT = 2
MAX_PAYABLE_INDIRECT_LEVEL = 4


def money(value):
    return Decimal(value or 0).quantize(MONEY_PLACES, rounding=ROUND_DOWN)


def percentage_amount(base_amount, percentage):
    return money(Decimal(base_amount or 0) * Decimal(percentage or 0) / Decimal('100'))


def get_completed_status():
    return SubscriptionStatusMaster.objects.filter(status_name='completed').first()


def is_completed_member(profile):
    return bool(
        profile
        and profile.subscription_status
        and profile.subscription_status.status_name == 'completed'
        and profile.subscription_plan_id
        and profile.is_active
    )


def get_latest_paid_order(profile):
    return profile.payment_orders.filter(
        status=PaymentOrder.StatusChoices.PAID,
    ).order_by('-paid_at', '-created_at').first()


def get_membership_reference(profile, paid_order=None):
    order = paid_order or get_latest_paid_order(profile)
    if order:
        return f'payment_order:{order.id}', order.amount
    plan_amount = profile.subscription_plan.plan_price if profile.subscription_plan else Decimal('0')
    return f'profile:{profile.id}:plan:{profile.subscription_plan_id}', plan_amount


def get_or_create_reward_points(profile):
    points, _ = RewardPoints.objects.select_for_update().get_or_create(user_profile=profile)
    if profile.points_id != points.id:
        profile.points = points
        profile.save(update_fields=['points', 'updated_at'])
    return points


def credit_reward_ledger(
    *,
    profile,
    reward_type,
    amount,
    idempotency_key,
    source_profile=None,
    subscription_plan=None,
    reward_subtype='',
    level=0,
    percentage_used=0,
    base_amount=0,
    calculated_amount=None,
    reference_id='',
    note='',
):
    amount = money(amount)
    calculated = money(calculated_amount if calculated_amount is not None else amount)

    with transaction.atomic():
        existing = RewardLedger.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            return existing, False

        points = get_or_create_reward_points(profile)
        if reward_type == RewardLedger.RewardType.LOYALTY:
            points.loyalty_reward = money(points.loyalty_reward + amount)
        elif reward_type == RewardLedger.RewardType.GLOBAL_POOL:
            points.global_pool_rewards = money(points.global_pool_rewards + amount)
        else:
            points.referral_rewards = money(points.referral_rewards + amount)

        balance_after = money(points.total_rewards)
        entry = RewardLedger.objects.create(
            user_profile=profile,
            source_user_profile=source_profile,
            subscription_plan=subscription_plan or profile.subscription_plan,
            reward_type=reward_type,
            reward_subtype=reward_subtype,
            level=level,
            percentage_used=Decimal(percentage_used or 0),
            base_amount=money(base_amount),
            calculated_amount=calculated,
            credited_amount=amount,
            balance_after=balance_after,
            reference_id=reference_id,
            note=note,
            idempotency_key=idempotency_key,
        )
        points.save(
            update_fields=[
                'loyalty_reward',
                'referral_rewards',
                'global_pool_rewards',
                'updated_at',
            ]
        )
        return entry, True


def ensure_referral_edge(child_profile):
    if not child_profile.referred_by_id or child_profile.referred_by_id == child_profile.id:
        return None

    edge, _ = ReferralEdge.objects.get_or_create(
        child=child_profile,
        defaults={
            'parent': child_profile.referred_by,
            'status': ReferralEdge.StatusChoices.PENDING,
        },
    )
    build_referral_closure(edge.parent, edge.child)
    return edge


def build_referral_closure(parent_profile, child_profile):
    if not parent_profile or not child_profile or parent_profile.id == child_profile.id:
        return

    ReferralClosure.objects.get_or_create(
        ancestor=parent_profile,
        descendant=child_profile,
        defaults={'depth': 1},
    )

    ancestor_links = ReferralClosure.objects.filter(descendant=parent_profile).select_related('ancestor')
    for link in ancestor_links:
        if link.ancestor_id == child_profile.id:
            continue
        ReferralClosure.objects.get_or_create(
            ancestor=link.ancestor,
            descendant=child_profile,
            defaults={'depth': link.depth + 1},
        )


def get_matching_reward_rule(reward_type, level, count):
    return RewardRule.objects.filter(
        reward_type=reward_type,
        level=level,
        min_count__lte=count,
        is_active=True,
    ).filter(
        Q(max_count__gte=count) | Q(max_count__isnull=True),
    ).order_by('-min_count').first()


def completed_direct_referral_count(profile):
    return ReferralEdge.objects.filter(
        parent=profile,
        status=ReferralEdge.StatusChoices.COMPLETED,
    ).count()


def completed_indirect_count(profile, depth):
    completed_status = get_completed_status()
    if not completed_status:
        return 0
    return ReferralClosure.objects.filter(
        ancestor=profile,
        depth=depth,
        descendant__subscription_status=completed_status,
        descendant__is_active=True,
    ).count()


def credit_direct_referral_reward(referrer, referred_profile, membership_reference):
    if not is_completed_member(referrer):
        return None, False

    count = completed_direct_referral_count(referrer)
    rule = get_matching_reward_rule(RewardRule.RewardType.DIRECT, 0, count)
    if not rule:
        return None, False

    base_amount = referrer.subscription_plan.plan_price
    amount = percentage_amount(base_amount, rule.percentage)
    if amount <= 0:
        return None, False

    entry, created = credit_reward_ledger(
        profile=referrer,
        source_profile=referred_profile,
        subscription_plan=referrer.subscription_plan,
        reward_type=RewardLedger.RewardType.DIRECT_REFERRAL,
        reward_subtype=f'Direct referral {rule.min_count}-{rule.max_count or "up"}',
        level=0,
        percentage_used=rule.percentage,
        base_amount=base_amount,
        calculated_amount=amount,
        amount=amount,
        reference_id=membership_reference,
        note='Direct referral reward credited after referred member approval.',
        idempotency_key=f'direct:{referrer.id}:{referred_profile.id}:{membership_reference}',
    )
    if created:
        create_notification_for_event(
            referrer,
            'direct_referral_reward_credited',
            context={
                'reward_amount': str(amount),
                'reward_percentage': str(rule.percentage),
                'referral_count': str(count),
            },
            dedupe_key=f'{referrer.id}:direct_referral_reward:{entry.id}',
        )
    return entry, created


def credit_indirect_referral_rewards(source_profile, membership_reference):
    created_entries = []
    ancestor_links = ReferralClosure.objects.filter(
        descendant=source_profile,
        depth__gte=2,
        depth__lte=MAX_PAYABLE_INDIRECT_LEVEL + 1,
    ).select_related('ancestor__subscription_plan', 'ancestor__subscription_status')

    for link in ancestor_links:
        ancestor = link.ancestor
        if not is_completed_member(ancestor):
            continue

        indirect_level = link.depth - 1
        count = completed_indirect_count(ancestor, link.depth)
        rule = get_matching_reward_rule(RewardRule.RewardType.INDIRECT, indirect_level, count)
        if not rule:
            continue

        base_amount = ancestor.subscription_plan.plan_price
        amount = percentage_amount(base_amount, rule.percentage)
        if amount <= 0:
            continue

        entry, created = credit_reward_ledger(
            profile=ancestor,
            source_profile=source_profile,
            subscription_plan=ancestor.subscription_plan,
            reward_type=RewardLedger.RewardType.INDIRECT_REFERRAL,
            reward_subtype=rule.role_name or f'Indirect level {indirect_level}',
            level=indirect_level,
            percentage_used=rule.percentage,
            base_amount=base_amount,
            calculated_amount=amount,
            amount=amount,
            reference_id=membership_reference,
            note='Indirect referral reward credited after network member approval.',
            idempotency_key=f'indirect:{ancestor.id}:{source_profile.id}:level:{indirect_level}:{membership_reference}',
        )
        if created:
            created_entries.append(entry)
            create_notification_for_event(
                ancestor,
                'indirect_referral_reward_credited',
                context={
                    'reward_amount': str(amount),
                    'reward_percentage': str(rule.percentage),
                    'referral_level': str(indirect_level),
                    'referral_role': rule.role_name,
                    'referral_count': str(count),
                },
                dedupe_key=f'{ancestor.id}:indirect_referral_reward:{entry.id}',
            )

    return created_entries


def get_active_global_pool_setting():
    setting = GlobalPoolSetting.objects.filter(is_active=True).order_by('-effective_from', '-created_at').first()
    if setting:
        return setting
    return GlobalPoolSetting.objects.create(
        membership_contribution_percentage=Decimal('0.00'),
        business_net_profit_amount=Decimal('0.00'),
        is_active=True,
    )


def create_global_pool_event(profile, trigger_type, paid_amount, membership_reference):
    setting = get_active_global_pool_setting()
    membership_pool_amount = percentage_amount(paid_amount, setting.membership_contribution_percentage)
    business_net_profit = money(setting.business_net_profit_amount)
    total_amount = money(membership_pool_amount + business_net_profit)
    idempotency_key = f'global_pool_event:{trigger_type}:{profile.id}:{membership_reference}'

    event, created = GlobalPoolEvent.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            'trigger_type': trigger_type,
            'trigger_user_profile': profile,
            'membership_reference': membership_reference,
            'paid_amount': money(paid_amount),
            'membership_percentage': setting.membership_contribution_percentage,
            'membership_pool_amount': membership_pool_amount,
            'business_net_profit_amount': business_net_profit,
            'total_distribution_amount': total_amount,
            'undistributed_amount': total_amount,
        },
    )
    if created and total_amount > 0:
        distribute_global_pool_event(event)
    return event, created


def get_active_pool_receivers(event):
    return list(
        GlobalPoolMember.objects.select_for_update()
        .select_related('user_profile')
        .filter(status=GlobalPoolMember.StatusChoices.ACTIVE)
        .exclude(user_profile=event.trigger_user_profile)
        .order_by('qualified_at', 'id')
    )


def distribute_global_pool_event(event):
    with transaction.atomic():
        event = GlobalPoolEvent.objects.select_for_update().get(pk=event.pk)
        if event.distributions.exists():
            return event

        receiver_members = [
            member for member in get_active_pool_receivers(event)
            if member.remaining_pool_capacity > 0
        ]
        remaining_amount = money(event.total_distribution_amount)
        credits = {member.id: Decimal('0.00') for member in receiver_members}
        before_capacity = {member.id: member.remaining_pool_capacity for member in receiver_members}

        active_members = {member.id: member for member in receiver_members}
        while remaining_amount > 0 and active_members:
            share = remaining_amount / Decimal(len(active_members))
            if share < MONEY_PLACES:
                break

            credited_this_round = Decimal('0.00')
            capped_member_ids = []

            for member_id, member in list(active_members.items()):
                capacity_left = before_capacity[member_id] - credits[member_id]
                raw_credit = min(share, capacity_left)
                credit = money(raw_credit)
                if credit <= 0:
                    capped_member_ids.append(member_id)
                    continue
                credits[member_id] = money(credits[member_id] + credit)
                credited_this_round = money(credited_this_round + credit)
                if credits[member_id] >= before_capacity[member_id]:
                    capped_member_ids.append(member_id)

            if credited_this_round <= 0:
                break

            remaining_amount = money(remaining_amount - credited_this_round)
            for member_id in capped_member_ids:
                active_members.pop(member_id, None)

            if not capped_member_ids:
                break

        distributed_amount = Decimal('0.00')
        for member in receiver_members:
            credited = money(credits[member.id])
            if credited <= 0:
                continue

            remaining_before = money(before_capacity[member.id])
            remaining_after = money(remaining_before - credited)
            GlobalPoolDistribution.objects.create(
                event=event,
                receiver=member.user_profile,
                calculated_share=credited,
                actual_credited=credited,
                remaining_limit_before=remaining_before,
                remaining_limit_after=remaining_after,
            )
            member.total_pool_earned = money(member.total_pool_earned + credited)
            if member.remaining_pool_capacity <= 0:
                member.status = GlobalPoolMember.StatusChoices.EXITED
                member.exited_at = timezone.now()
            member.save(update_fields=['total_pool_earned', 'status', 'exited_at', 'updated_at'])
            distributed_amount = money(distributed_amount + credited)

            entry, created = credit_reward_ledger(
                profile=member.user_profile,
                source_profile=event.trigger_user_profile,
                subscription_plan=member.current_plan,
                reward_type=RewardLedger.RewardType.GLOBAL_POOL,
                reward_subtype=event.trigger_type,
                amount=credited,
                calculated_amount=credited,
                reference_id=f'global_pool_event:{event.id}',
                note='Global pool reward credited from membership contribution and business net profit.',
                idempotency_key=f'global_pool:{event.id}:{member.user_profile_id}',
            )
            if created:
                create_notification_for_event(
                    member.user_profile,
                    'global_pool_reward_credited',
                    context={
                        'reward_amount': str(credited),
                        'global_pool_balance': str(member.total_pool_earned),
                        'global_pool_limit': str(member.max_pool_limit),
                    },
                    dedupe_key=f'{member.user_profile_id}:global_pool_reward:{entry.id}',
                )

        event.distributed_amount = distributed_amount
        event.undistributed_amount = money(event.total_distribution_amount - distributed_amount)
        event.save(update_fields=['distributed_amount', 'undistributed_amount'])
        return event


def upsert_global_pool_member(profile, direct_count, paid_amount, membership_reference):
    if not profile.subscription_plan_id:
        return None, False

    new_limit = money(profile.subscription_plan.global_pool_limit)
    now = timezone.now()

    with transaction.atomic():
        member = GlobalPoolMember.objects.select_for_update().filter(user_profile=profile).first()
        if not member:
            event, event_created = create_global_pool_event(
                profile,
                GlobalPoolEvent.TriggerType.NEW_POOL_MEMBER,
                paid_amount,
                membership_reference,
            )
            member = GlobalPoolMember.objects.create(
                user_profile=profile,
                qualified_at=now,
                qualified_by_direct_referrals_count=direct_count,
                current_plan=profile.subscription_plan,
                max_pool_limit=new_limit,
                total_pool_earned=Decimal('0.00'),
                status=GlobalPoolMember.StatusChoices.ACTIVE if new_limit > 0 else GlobalPoolMember.StatusChoices.EXITED,
                exited_at=now if new_limit <= 0 else None,
            )
            create_notification_for_event(
                profile,
                'global_pool_qualified',
                context={
                    'referral_count': str(direct_count),
                    'global_pool_limit': str(new_limit),
                },
                dedupe_key=f'{profile.id}:global_pool_qualified',
            )
            return member, event_created

        old_limit = member.max_pool_limit
        member.current_plan = profile.subscription_plan
        member.max_pool_limit = new_limit
        member.qualified_by_direct_referrals_count = max(member.qualified_by_direct_referrals_count, direct_count)
        if member.total_pool_earned < new_limit:
            if member.status == GlobalPoolMember.StatusChoices.EXITED:
                member.last_reactivated_at = now
            member.status = GlobalPoolMember.StatusChoices.ACTIVE
            member.exited_at = None
        else:
            member.status = GlobalPoolMember.StatusChoices.EXITED
            member.exited_at = member.exited_at or now
        member.save(
            update_fields=[
                'current_plan',
                'max_pool_limit',
                'qualified_by_direct_referrals_count',
                'status',
                'last_reactivated_at',
                'exited_at',
                'updated_at',
            ]
        )

    trigger_type = (
        GlobalPoolEvent.TriggerType.UPGRADE
        if new_limit > old_limit
        else GlobalPoolEvent.TriggerType.RECHARGE
    )
    event, event_created = create_global_pool_event(profile, trigger_type, paid_amount, membership_reference)
    return member, event_created


def evaluate_global_pool_for_profile(profile, paid_amount=None, membership_reference=''):
    if not is_completed_member(profile):
        return None, False

    direct_count = completed_direct_referral_count(profile)
    if direct_count < DIRECT_REFERRAL_TO_POOL_COUNT:
        return None, False

    if not membership_reference:
        membership_reference, fallback_amount = get_membership_reference(profile)
        paid_amount = paid_amount if paid_amount is not None else fallback_amount

    return upsert_global_pool_member(
        profile,
        direct_count,
        money(paid_amount),
        membership_reference,
    )


def complete_referral_rewards_for_profile(profile, membership_reference):
    edge = ensure_referral_edge(profile)
    if not edge:
        return []

    with transaction.atomic():
        edge = ReferralEdge.objects.select_for_update().select_related('parent', 'child').get(pk=edge.pk)
        if edge.status != ReferralEdge.StatusChoices.COMPLETED:
            edge.status = ReferralEdge.StatusChoices.COMPLETED
            edge.completed_at = timezone.now()
            edge.source_membership_reference = membership_reference
            edge.save(update_fields=['status', 'completed_at', 'source_membership_reference', 'updated_at'])

    entries = []
    direct_entry, direct_created = credit_direct_referral_reward(edge.parent, profile, membership_reference)
    if direct_created:
        entries.append(direct_entry)
    entries.extend(credit_indirect_referral_rewards(profile, membership_reference))
    evaluate_global_pool_for_profile(edge.parent)
    return entries


def process_approved_membership(profile, paid_order=None):
    profile = UserProfile.objects.select_related(
        'subscription_plan',
        'subscription_status',
        'referred_by',
    ).get(pk=profile.pk)
    if not is_completed_member(profile):
        return {'processed': False, 'reason': 'profile is not completed'}

    membership_reference, paid_amount = get_membership_reference(profile, paid_order)
    ensure_referral_edge(profile)
    referral_entries = complete_referral_rewards_for_profile(profile, membership_reference)
    pool_member, pool_event_created = evaluate_global_pool_for_profile(
        profile,
        paid_amount=paid_amount,
        membership_reference=membership_reference,
    )

    return {
        'processed': True,
        'referral_entries': len(referral_entries),
        'pool_member_id': pool_member.id if pool_member else None,
        'pool_event_created': pool_event_created,
    }
