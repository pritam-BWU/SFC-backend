from django.contrib import admin

from .models import (
    AdminAccount,
    GlobalPoolDistribution,
    GlobalPoolEvent,
    GlobalPoolMember,
    GlobalPoolSetting,
    IssueReport,
    IssueReportDocument,
    LoyaltyRewardLedger,
    NotificationEventMaster,
    NotificationRule,
    PaymentOrder,
    PaymentProvider,
    PaymentRefund,
    PaymentTransaction,
    PaymentWebhookEvent,
    ReferralClosure,
    ReferralEdge,
    RewardLedger,
    RewardPoints,
    RewardRule,
    SubscriptionMasterPlan,
    SubscriptionStatusMaster,
    UserLoyaltyAccount,
    UserNotification,
    UserProfile,
)


@admin.register(AdminAccount)
class AdminAccountAdmin(admin.ModelAdmin):
    list_display = ('username', 'name', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('username', 'name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(SubscriptionMasterPlan)
class SubscriptionMasterPlanAdmin(admin.ModelAdmin):
    list_display = ('plan_name', 'plan_price', 'monthly_reward', 'yearly_reward', 'refundable', 'non_refundable', 'created_at')
    list_filter = ('refundable', 'non_refundable', 'created_at')
    search_fields = ('plan_name',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(SubscriptionStatusMaster)
class SubscriptionStatusMasterAdmin(admin.ModelAdmin):
    list_display = ('status_name', 'created_at')
    search_fields = ('status_name',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(NotificationEventMaster)
class NotificationEventMasterAdmin(admin.ModelAdmin):
    list_display = ('event_key', 'event_name', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('event_key', 'event_name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(NotificationRule)
class NotificationRuleAdmin(admin.ModelAdmin):
    list_display = ('event', 'is_active', 'send_immediately', 'updated_at')
    list_filter = ('is_active', 'send_immediately', 'event')
    search_fields = ('event__event_key', 'event__event_name', 'title_template')
    readonly_fields = ('created_at', 'updated_at')
    autocomplete_fields = ('event',)


@admin.register(UserNotification)
class UserNotificationAdmin(admin.ModelAdmin):
    list_display = ('user_profile', 'event', 'title', 'is_read', 'created_at')
    list_filter = ('is_read', 'event', 'created_at')
    search_fields = ('user_profile__id', 'user_profile__full_name', 'title', 'message')
    readonly_fields = ('created_at',)
    autocomplete_fields = ('user_profile', 'event', 'created_by_rule')


@admin.register(IssueReport)
class IssueReportAdmin(admin.ModelAdmin):
    list_display = ('report_id', 'user_profile', 'status', 'created_at', 'updated_at')
    list_filter = ('status', 'created_at', 'updated_at')
    search_fields = ('report_id', 'user_profile__id', 'user_profile__full_name', 'description')
    readonly_fields = ('report_id', 'created_at', 'updated_at')
    autocomplete_fields = ('user_profile',)


@admin.register(IssueReportDocument)
class IssueReportDocumentAdmin(admin.ModelAdmin):
    list_display = ('original_name', 'issue_report', 'uploaded_at')
    search_fields = ('original_name', 'file_url', 'issue_report__report_id')
    readonly_fields = ('id', 'uploaded_at')
    autocomplete_fields = ('issue_report',)


@admin.register(PaymentProvider)
class PaymentProviderAdmin(admin.ModelAdmin):
    list_display = ('provider_name', 'provider_key', 'mode', 'is_active', 'created_at')
    list_filter = ('mode', 'is_active', 'created_at')
    search_fields = ('provider_name', 'provider_key')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(PaymentOrder)
class PaymentOrderAdmin(admin.ModelAdmin):
    list_display = ('receipt', 'user_profile', 'subscription_plan', 'amount', 'currency', 'status', 'gateway_order_id', 'created_at')
    list_filter = ('status', 'provider', 'currency', 'created_at')
    search_fields = ('receipt', 'gateway_order_id', 'user_profile__id', 'user_profile__full_name')
    readonly_fields = ('created_at', 'updated_at', 'paid_at', 'cancelled_at')
    autocomplete_fields = ('user_profile', 'subscription_plan', 'provider')


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ('gateway_payment_id', 'payment_order', 'user_profile', 'amount', 'status', 'payment_method', 'paid_at')
    list_filter = ('status', 'provider', 'payment_method', 'created_at')
    search_fields = ('gateway_payment_id', 'payment_order__receipt', 'user_profile__id', 'user_profile__full_name')
    readonly_fields = ('created_at', 'updated_at')
    autocomplete_fields = ('payment_order', 'user_profile', 'provider')


@admin.register(PaymentRefund)
class PaymentRefundAdmin(admin.ModelAdmin):
    list_display = ('gateway_refund_id', 'payment_order', 'user_profile', 'amount', 'status', 'requested_at', 'processed_at')
    list_filter = ('status', 'provider', 'requested_at')
    search_fields = ('gateway_refund_id', 'payment_order__receipt', 'user_profile__id', 'user_profile__full_name')
    readonly_fields = ('requested_at', 'created_at', 'updated_at')
    autocomplete_fields = ('payment_order', 'payment_transaction', 'user_profile', 'provider', 'requested_by')


@admin.register(PaymentWebhookEvent)
class PaymentWebhookEventAdmin(admin.ModelAdmin):
    list_display = ('event_name', 'provider', 'event_id', 'is_valid_signature', 'is_processed', 'received_at')
    list_filter = ('event_name', 'provider', 'is_valid_signature', 'is_processed', 'received_at')
    search_fields = ('event_id', 'event_name')
    readonly_fields = ('received_at', 'processed_at')
    autocomplete_fields = ('provider',)


@admin.register(UserLoyaltyAccount)
class UserLoyaltyAccountAdmin(admin.ModelAdmin):
    list_display = ('user_profile', 'balance', 'lifetime_earned', 'lifetime_redeemed', 'updated_at')
    list_filter = ('created_at', 'updated_at')
    search_fields = ('user_profile__id', 'user_profile__full_name', 'user_profile__user__username')
    readonly_fields = ('created_at', 'updated_at')
    autocomplete_fields = ('user_profile',)


@admin.register(RewardPoints)
class RewardPointsAdmin(admin.ModelAdmin):
    list_display = ('id', 'user_profile', 'loyalty_reward', 'referral_rewards', 'global_pool_rewards', 'updated_at')
    list_filter = ('created_at', 'updated_at')
    search_fields = ('=id', 'user_profile__id', 'user_profile__full_name', 'user_profile__user__username')
    readonly_fields = ('created_at', 'updated_at')
    autocomplete_fields = ('user_profile',)


@admin.register(ReferralEdge)
class ReferralEdgeAdmin(admin.ModelAdmin):
    list_display = ('parent', 'child', 'status', 'completed_at', 'created_at')
    list_filter = ('status', 'created_at', 'completed_at')
    search_fields = ('parent__id', 'parent__full_name', 'child__id', 'child__full_name')
    readonly_fields = ('created_at', 'updated_at')
    autocomplete_fields = ('parent', 'child')


@admin.register(ReferralClosure)
class ReferralClosureAdmin(admin.ModelAdmin):
    list_display = ('ancestor', 'descendant', 'depth', 'created_at')
    list_filter = ('depth', 'created_at')
    search_fields = ('ancestor__id', 'ancestor__full_name', 'descendant__id', 'descendant__full_name')
    readonly_fields = ('created_at',)
    autocomplete_fields = ('ancestor', 'descendant')


@admin.register(RewardRule)
class RewardRuleAdmin(admin.ModelAdmin):
    list_display = ('reward_type', 'level', 'role_name', 'min_count', 'max_count', 'percentage', 'is_active')
    list_filter = ('reward_type', 'level', 'is_active')
    search_fields = ('role_name',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(RewardLedger)
class RewardLedgerAdmin(admin.ModelAdmin):
    list_display = ('user_profile', 'reward_type', 'reward_subtype', 'level', 'credited_amount', 'balance_after', 'created_at')
    list_filter = ('reward_type', 'reward_subtype', 'status', 'created_at')
    search_fields = ('user_profile__id', 'user_profile__full_name', 'reference_id', 'idempotency_key')
    readonly_fields = ('created_at',)
    autocomplete_fields = ('user_profile', 'source_user_profile', 'subscription_plan')


@admin.register(GlobalPoolSetting)
class GlobalPoolSettingAdmin(admin.ModelAdmin):
    list_display = ('membership_contribution_percentage', 'business_net_profit_amount', 'is_active', 'effective_from')
    list_filter = ('is_active', 'effective_from')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(GlobalPoolMember)
class GlobalPoolMemberAdmin(admin.ModelAdmin):
    list_display = ('user_profile', 'current_plan', 'status', 'max_pool_limit', 'total_pool_earned', 'qualified_at')
    list_filter = ('status', 'current_plan', 'qualified_at')
    search_fields = ('user_profile__id', 'user_profile__full_name')
    readonly_fields = ('created_at', 'updated_at')
    autocomplete_fields = ('user_profile', 'current_plan')


@admin.register(GlobalPoolEvent)
class GlobalPoolEventAdmin(admin.ModelAdmin):
    list_display = ('trigger_type', 'trigger_user_profile', 'paid_amount', 'total_distribution_amount', 'distributed_amount', 'undistributed_amount', 'created_at')
    list_filter = ('trigger_type', 'created_at')
    search_fields = ('trigger_user_profile__id', 'trigger_user_profile__full_name', 'membership_reference', 'idempotency_key')
    readonly_fields = ('created_at',)
    autocomplete_fields = ('trigger_user_profile',)


@admin.register(GlobalPoolDistribution)
class GlobalPoolDistributionAdmin(admin.ModelAdmin):
    list_display = ('event', 'receiver', 'actual_credited', 'remaining_limit_before', 'remaining_limit_after', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('receiver__id', 'receiver__full_name')
    readonly_fields = ('created_at',)
    autocomplete_fields = ('event', 'receiver')


@admin.register(LoyaltyRewardLedger)
class LoyaltyRewardLedgerAdmin(admin.ModelAdmin):
    list_display = ('user_profile', 'entry_type', 'reward_preference', 'amount', 'balance_after', 'period_key', 'source', 'created_at')
    list_filter = ('entry_type', 'reward_preference', 'source', 'created_at')
    search_fields = ('user_profile__id', 'user_profile__full_name', 'reference_id', 'period_key')
    readonly_fields = ('created_at',)
    autocomplete_fields = ('user_profile', 'account', 'subscription_plan')


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'full_name',
        'username',
        'phone_number',
        'email_address',
        'subscription_plan',
        'subscription_status',
        'referral_code',
        'points',
        'loyalty_reward_preference',
        'is_active',
        'created_at',
    )
    list_filter = ('gender', 'is_active', 'subscription_plan', 'subscription_status', 'loyalty_reward_preference', 'created_at')
    search_fields = (
        'user__username',
        'id',
        'full_name',
        'phone_number',
        'email_address',
        'pan_no',
        'referral_code',
    )
    readonly_fields = ('id', 'created_at', 'updated_at')
    autocomplete_fields = ('user', 'subscription_plan', 'subscription_status', 'referred_by', 'points')

    @admin.display(ordering='user__username')
    def username(self, obj):
        return obj.user.username
