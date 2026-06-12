from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.utils import timezone
import uuid


class SubscriptionMasterPlan(models.Model):
    id = models.AutoField(primary_key=True)
    plan_name = models.CharField(max_length=120)
    plan_price = models.DecimalField(max_digits=10, decimal_places=2)
    monthly_reward = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    yearly_reward = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    global_pool_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    refundable = models.BooleanField(default=False)
    non_refundable = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'subscription_master_plans'
        ordering = ['plan_price', 'plan_name']

    def __str__(self):
        return self.plan_name


class SubscriptionStatusMaster(models.Model):
    id = models.AutoField(primary_key=True)
    status_name = models.CharField(max_length=50, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'subscription_status_master'
        ordering = ['id']

    def __str__(self):
        return self.status_name


class NotificationEventMaster(models.Model):
    id = models.AutoField(primary_key=True)
    event_key = models.CharField(max_length=80, unique=True)
    event_name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'notification_event_master'
        ordering = ['id']

    def __str__(self):
        return self.event_name


class NotificationRule(models.Model):
    id = models.AutoField(primary_key=True)
    event = models.OneToOneField(
        NotificationEventMaster,
        on_delete=models.CASCADE,
        related_name='rule',
    )
    title_template = models.CharField(max_length=180)
    message_template = models.TextField()
    deep_link = models.CharField(max_length=255, blank=True)
    send_immediately = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'notification_rule'
        ordering = ['event__id']

    def __str__(self):
        return f'{self.event.event_name} rule'


class AdminAccount(models.Model):
    id = models.AutoField(primary_key=True)
    username = models.CharField(max_length=150, unique=True)
    password = models.CharField(max_length=128)
    name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'admin_table'
        ordering = ['username']

    def __str__(self):
        return self.name

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)

    def save(self, *args, **kwargs):
        if self.password and not self.password.startswith(('pbkdf2_', 'argon2$', 'bcrypt')):
            self.set_password(self.password)
        super().save(*args, **kwargs)


class UserProfile(models.Model):
    class GenderChoices(models.TextChoices):
        MALE = 'M', 'Male'
        FEMALE = 'F', 'Female'
        OTHER = 'O', 'Other'

    class LoyaltyRewardPreference(models.IntegerChoices):
        MONTHLY = 0, 'Monthly'
        YEARLY = 1, 'Yearly'

    id = models.CharField(max_length=20, primary_key=True, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
    )
    full_name = models.CharField(max_length=150)
    dob = models.DateField(blank=True, null=True)
    pan_no = models.CharField(max_length=20, blank=True)
    gender = models.CharField(
        max_length=1,
        choices=GenderChoices.choices,
        blank=True,
    )
    nationality = models.CharField(max_length=80, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=80, blank=True)
    state = models.CharField(max_length=80, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    email_address = models.EmailField(blank=True)
    nominee_full_name = models.CharField(max_length=150, blank=True)
    nominee_relationship = models.CharField(max_length=80, blank=True)
    nominee_phone_number = models.CharField(max_length=20, blank=True)
    how_did_you_hear_about_club = models.CharField(max_length=150, blank=True)
    payment_details = models.TextField(blank=True)
    uploaded_form_document = models.ImageField(
        upload_to='user_documents/',
        blank=True,
        null=True,
    )
    subscription_plan = models.ForeignKey(
        SubscriptionMasterPlan,
        on_delete=models.SET_NULL,
        related_name='user_profiles',
        blank=True,
        null=True,
    )
    subscription_status = models.ForeignKey(
        SubscriptionStatusMaster,
        on_delete=models.SET_NULL,
        related_name='user_profiles',
        blank=True,
        null=True,
    )
    referral_code = models.CharField(max_length=30, unique=True, blank=True, db_index=True)
    referred_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        related_name='referred_profiles',
        blank=True,
        null=True,
    )
    points = models.OneToOneField(
        'RewardPoints',
        on_delete=models.SET_NULL,
        related_name='profile_points_owner',
        blank=True,
        null=True,
    )
    loyalty_reward_preference = models.SmallIntegerField(
        choices=LoyaltyRewardPreference.choices,
        blank=True,
        null=True,
    )
    loyalty_preference_selected_at = models.DateTimeField(blank=True, null=True)
    loyalty_preference_locked_until = models.DateField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_profile'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.full_name} ({self.user.username})'

    @classmethod
    def generate_membership_id(cls):
        year = timezone.localdate().year
        prefix = f'SFC-{year}-'
        last_profile = cls.objects.filter(id__startswith=prefix).order_by('-id').first()
        next_number = 1

        if last_profile:
            try:
                next_number = int(last_profile.id.rsplit('-', 1)[1]) + 1
            except (IndexError, ValueError):
                next_number = 1

        return f'{prefix}{next_number:04d}'

    def save(self, *args, **kwargs):
        if not self.id:
            self.id = self.generate_membership_id()
        if not self.referral_code:
            self.referral_code = generate_referral_code()
            while UserProfile.objects.filter(referral_code=self.referral_code).exists():
                self.referral_code = generate_referral_code()
        super().save(*args, **kwargs)


class IssueReport(models.Model):
    class StatusChoices(models.TextChoices):
        OPEN = 'OPEN', 'Open'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        CLOSED = 'CLOSED', 'Closed'

    id = models.BigAutoField(primary_key=True)
    user_profile = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='issue_reports',
    )
    report_id = models.CharField(max_length=30, unique=True, editable=False)
    description = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=StatusChoices.choices,
        default=StatusChoices.OPEN,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'issue_reports'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user_profile', 'status']),
            models.Index(fields=['report_id']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f'{self.report_id} - {self.user_profile_id}'

    @classmethod
    def generate_report_id(cls):
        year = timezone.localdate().year
        prefix = f'RPT-{year}-'
        last_report = cls.objects.filter(report_id__startswith=prefix).order_by('-report_id').first()
        next_number = 1

        if last_report:
            try:
                next_number = int(last_report.report_id.rsplit('-', 1)[1]) + 1
            except (IndexError, ValueError):
                next_number = 1

        return f'{prefix}{next_number:06d}'

    def save(self, *args, **kwargs):
        if not self.report_id:
            self.report_id = self.generate_report_id()
        super().save(*args, **kwargs)


class IssueReportDocument(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    issue_report = models.ForeignKey(
        IssueReport,
        on_delete=models.CASCADE,
        related_name='documents',
    )
    file_url = models.TextField()
    original_name = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'issue_report_documents'
        ordering = ['uploaded_at']

    def __str__(self):
        return self.original_name


class RewardPoints(models.Model):
    id = models.AutoField(primary_key=True)
    user_profile = models.OneToOneField(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='reward_points',
    )
    loyalty_reward = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    referral_rewards = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    global_pool_rewards = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'rewards'
        ordering = ['-updated_at']

    def __str__(self):
        return f'{self.user_profile_id} rewards'

    @property
    def total_rewards(self):
        return self.loyalty_reward + self.referral_rewards + self.global_pool_rewards


class UserLoyaltyAccount(models.Model):
    id = models.AutoField(primary_key=True)
    user_profile = models.OneToOneField(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='loyalty_account',
    )
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    lifetime_earned = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    lifetime_redeemed = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    last_monthly_credit_at = models.DateTimeField(blank=True, null=True)
    last_yearly_credit_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_loyalty_account'
        ordering = ['-updated_at']

    def __str__(self):
        return f'{self.user_profile_id} loyalty account'


class LoyaltyRewardLedger(models.Model):
    class EntryType(models.TextChoices):
        CREDIT = 'credit', 'Credit'
        DEBIT = 'debit', 'Debit'
        ADJUSTMENT = 'adjustment', 'Adjustment'

    class SourceChoices(models.TextChoices):
        SYSTEM = 'system', 'System'
        ADMIN = 'admin', 'Admin'
        MOBILE_APP = 'mobile_app', 'Mobile App'
        PAYMENT = 'payment', 'Payment'

    id = models.AutoField(primary_key=True)
    user_profile = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='loyalty_ledger_entries',
    )
    account = models.ForeignKey(
        UserLoyaltyAccount,
        on_delete=models.CASCADE,
        related_name='ledger_entries',
    )
    subscription_plan = models.ForeignKey(
        SubscriptionMasterPlan,
        on_delete=models.SET_NULL,
        related_name='loyalty_ledger_entries',
        blank=True,
        null=True,
    )
    entry_type = models.CharField(max_length=20, choices=EntryType.choices, default=EntryType.CREDIT)
    reward_preference = models.SmallIntegerField(choices=UserProfile.LoyaltyRewardPreference.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    period_key = models.CharField(max_length=20)
    reference_id = models.CharField(max_length=120, blank=True)
    source = models.CharField(max_length=30, choices=SourceChoices.choices, default=SourceChoices.SYSTEM)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'loyalty_reward_ledger'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user_profile', 'reward_preference', 'period_key', 'entry_type'],
                name='unique_loyalty_reward_period',
            ),
        ]
        indexes = [
            models.Index(fields=['user_profile', 'created_at']),
            models.Index(fields=['period_key', 'entry_type']),
        ]

    def __str__(self):
        return f'{self.user_profile_id} {self.entry_type} {self.amount}'


class PaymentProvider(models.Model):
    class ModeChoices(models.TextChoices):
        TEST = 'test', 'Test'
        LIVE = 'live', 'Live'

    id = models.AutoField(primary_key=True)
    provider_key = models.CharField(max_length=50, unique=True)
    provider_name = models.CharField(max_length=120)
    mode = models.CharField(max_length=10, choices=ModeChoices.choices, default=ModeChoices.TEST)
    is_active = models.BooleanField(default=True)
    config = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'payment_provider'
        ordering = ['provider_name']

    def __str__(self):
        return self.provider_name


def generate_payment_receipt():
    return f'SFC-RCP-{timezone.localdate().year}-{uuid.uuid4().hex[:10].upper()}'


def generate_referral_code():
    return f'SFC{uuid.uuid4().hex[:8].upper()}'


class PaymentOrder(models.Model):
    class StatusChoices(models.TextChoices):
        CREATED = 'created', 'Created'
        ATTEMPTED = 'attempted', 'Attempted'
        PAID = 'paid', 'Paid'
        FAILED = 'failed', 'Failed'
        CANCELLED = 'cancelled', 'Cancelled'
        REFUNDED = 'refunded', 'Refunded'

    id = models.AutoField(primary_key=True)
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='payment_orders')
    subscription_plan = models.ForeignKey(
        SubscriptionMasterPlan,
        on_delete=models.SET_NULL,
        related_name='payment_orders',
        blank=True,
        null=True,
    )
    provider = models.ForeignKey(PaymentProvider, on_delete=models.PROTECT, related_name='payment_orders')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='INR')
    receipt = models.CharField(max_length=40, unique=True, default=generate_payment_receipt)
    gateway_order_id = models.CharField(max_length=120, blank=True, db_index=True)
    status = models.CharField(max_length=20, choices=StatusChoices.choices, default=StatusChoices.CREATED, db_index=True)
    notes = models.JSONField(default=dict, blank=True)
    raw_gateway_response = models.JSONField(default=dict, blank=True)
    paid_at = models.DateTimeField(blank=True, null=True)
    cancelled_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'payment_order'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user_profile', 'status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f'{self.receipt} - {self.user_profile_id}'


class PaymentTransaction(models.Model):
    class StatusChoices(models.TextChoices):
        CREATED = 'created', 'Created'
        AUTHORIZED = 'authorized', 'Authorized'
        CAPTURED = 'captured', 'Captured'
        FAILED = 'failed', 'Failed'
        REFUNDED = 'refunded', 'Refunded'

    id = models.AutoField(primary_key=True)
    payment_order = models.ForeignKey(PaymentOrder, on_delete=models.CASCADE, related_name='transactions')
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='payment_transactions')
    provider = models.ForeignKey(PaymentProvider, on_delete=models.PROTECT, related_name='payment_transactions')
    gateway_payment_id = models.CharField(max_length=120, unique=True, blank=True, null=True)
    gateway_signature = models.CharField(max_length=255, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='INR')
    status = models.CharField(max_length=20, choices=StatusChoices.choices, default=StatusChoices.CREATED, db_index=True)
    payment_method = models.CharField(max_length=50, blank=True)
    bank = models.CharField(max_length=80, blank=True)
    wallet = models.CharField(max_length=80, blank=True)
    vpa = models.CharField(max_length=120, blank=True)
    card_network = models.CharField(max_length=50, blank=True)
    card_last4 = models.CharField(max_length=4, blank=True)
    fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    gateway_status = models.CharField(max_length=80, blank=True)
    error_code = models.CharField(max_length=120, blank=True)
    error_description = models.TextField(blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    paid_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'payment_transaction'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user_profile', 'status']),
            models.Index(fields=['payment_order', 'status']),
        ]

    def __str__(self):
        return self.gateway_payment_id or f'Transaction {self.id}'


class PaymentRefund(models.Model):
    class StatusChoices(models.TextChoices):
        REQUESTED = 'requested', 'Requested'
        PROCESSED = 'processed', 'Processed'
        FAILED = 'failed', 'Failed'
        CANCELLED = 'cancelled', 'Cancelled'

    id = models.AutoField(primary_key=True)
    payment_order = models.ForeignKey(PaymentOrder, on_delete=models.CASCADE, related_name='refunds')
    payment_transaction = models.ForeignKey(PaymentTransaction, on_delete=models.SET_NULL, related_name='refunds', blank=True, null=True)
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='payment_refunds')
    provider = models.ForeignKey(PaymentProvider, on_delete=models.PROTECT, related_name='payment_refunds')
    gateway_refund_id = models.CharField(max_length=120, blank=True, db_index=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='INR')
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=StatusChoices.choices, default=StatusChoices.REQUESTED, db_index=True)
    requested_by = models.ForeignKey(AdminAccount, on_delete=models.SET_NULL, related_name='requested_refunds', blank=True, null=True)
    raw_gateway_response = models.JSONField(default=dict, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'payment_refund'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user_profile', 'status']),
            models.Index(fields=['payment_order', 'status']),
        ]

    def __str__(self):
        return self.gateway_refund_id or f'Refund {self.id}'


class PaymentWebhookEvent(models.Model):
    id = models.AutoField(primary_key=True)
    provider = models.ForeignKey(PaymentProvider, on_delete=models.PROTECT, related_name='webhook_events')
    event_id = models.CharField(max_length=120, blank=True, null=True, unique=True)
    event_name = models.CharField(max_length=120)
    signature = models.CharField(max_length=255, blank=True)
    payload = models.JSONField(default=dict)
    headers = models.JSONField(default=dict, blank=True)
    is_valid_signature = models.BooleanField(default=False)
    is_processed = models.BooleanField(default=False)
    processing_error = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'payment_webhook_event'
        ordering = ['-received_at']
        indexes = [
            models.Index(fields=['event_name', 'is_processed']),
            models.Index(fields=['received_at']),
        ]

    def __str__(self):
        return self.event_name


class UserNotification(models.Model):
    id = models.AutoField(primary_key=True)
    user_profile = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    event = models.ForeignKey(
        NotificationEventMaster,
        on_delete=models.SET_NULL,
        related_name='user_notifications',
        blank=True,
        null=True,
    )
    created_by_rule = models.ForeignKey(
        NotificationRule,
        on_delete=models.SET_NULL,
        related_name='user_notifications',
        blank=True,
        null=True,
    )
    title = models.CharField(max_length=180)
    message = models.TextField()
    deep_link = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    dedupe_key = models.CharField(max_length=180, unique=True, blank=True, null=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'user_notification'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user_profile', 'is_read']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f'{self.user_profile_id}: {self.title}'


class ReferralEdge(models.Model):
    class StatusChoices(models.TextChoices):
        PENDING = 'pending', 'Pending'
        COMPLETED = 'completed', 'Completed'

    id = models.AutoField(primary_key=True)
    parent = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='direct_referrals',
    )
    child = models.OneToOneField(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='referral_parent_edge',
    )
    status = models.CharField(max_length=20, choices=StatusChoices.choices, default=StatusChoices.PENDING)
    completed_at = models.DateTimeField(blank=True, null=True)
    source_membership_reference = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'referral_edges'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['parent', 'status']),
            models.Index(fields=['child', 'status']),
        ]

    def __str__(self):
        return f'{self.parent_id} -> {self.child_id}'


class ReferralClosure(models.Model):
    id = models.AutoField(primary_key=True)
    ancestor = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='referral_descendant_links',
    )
    descendant = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='referral_ancestor_links',
    )
    depth = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'referral_closure'
        constraints = [
            models.UniqueConstraint(fields=['ancestor', 'descendant'], name='unique_referral_closure_pair'),
        ]
        indexes = [
            models.Index(fields=['ancestor', 'depth']),
            models.Index(fields=['descendant', 'depth']),
        ]

    def __str__(self):
        return f'{self.ancestor_id} -> {self.descendant_id} ({self.depth})'


class RewardRule(models.Model):
    class RewardType(models.TextChoices):
        DIRECT = 'direct_referral', 'Direct Referral'
        INDIRECT = 'indirect_referral', 'Indirect Referral'

    id = models.AutoField(primary_key=True)
    reward_type = models.CharField(max_length=30, choices=RewardType.choices)
    level = models.PositiveSmallIntegerField(default=0)
    role_name = models.CharField(max_length=80, blank=True)
    min_count = models.PositiveIntegerField()
    max_count = models.PositiveIntegerField(blank=True, null=True)
    percentage = models.DecimalField(max_digits=6, decimal_places=3)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'reward_rules'
        ordering = ['reward_type', 'level', 'min_count']
        indexes = [
            models.Index(fields=['reward_type', 'level', 'min_count', 'max_count']),
        ]

    def __str__(self):
        limit = self.max_count if self.max_count else 'up'
        return f'{self.get_reward_type_display()} L{self.level} {self.min_count}-{limit}: {self.percentage}%'


class RewardLedger(models.Model):
    class RewardType(models.TextChoices):
        LOYALTY = 'loyalty', 'Loyalty'
        DIRECT_REFERRAL = 'direct_referral', 'Direct Referral'
        INDIRECT_REFERRAL = 'indirect_referral', 'Indirect Referral'
        GLOBAL_POOL = 'global_pool', 'Global Pool'

    class StatusChoices(models.TextChoices):
        CREDITED = 'credited', 'Credited'
        SKIPPED = 'skipped', 'Skipped'
        REVERSED = 'reversed', 'Reversed'

    id = models.AutoField(primary_key=True)
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='reward_ledger_entries')
    source_user_profile = models.ForeignKey(
        UserProfile,
        on_delete=models.SET_NULL,
        related_name='triggered_reward_ledger_entries',
        blank=True,
        null=True,
    )
    subscription_plan = models.ForeignKey(
        SubscriptionMasterPlan,
        on_delete=models.SET_NULL,
        related_name='reward_ledger_entries',
        blank=True,
        null=True,
    )
    reward_type = models.CharField(max_length=30, choices=RewardType.choices)
    reward_subtype = models.CharField(max_length=80, blank=True)
    level = models.PositiveSmallIntegerField(default=0)
    percentage_used = models.DecimalField(max_digits=7, decimal_places=3, default=0)
    base_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    calculated_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    credited_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reference_id = models.CharField(max_length=120, blank=True)
    note = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=StatusChoices.choices, default=StatusChoices.CREDITED)
    idempotency_key = models.CharField(max_length=180, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'reward_ledger'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user_profile', 'reward_type', 'created_at']),
            models.Index(fields=['reference_id']),
        ]

    def __str__(self):
        return f'{self.user_profile_id} {self.reward_type} {self.credited_amount}'


class GlobalPoolSetting(models.Model):
    id = models.AutoField(primary_key=True)
    membership_contribution_percentage = models.DecimalField(max_digits=6, decimal_places=3, default=0)
    business_net_profit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    effective_from = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'global_pool_settings'
        ordering = ['-effective_from', '-created_at']

    def __str__(self):
        return f'{self.membership_contribution_percentage}% + Rs. {self.business_net_profit_amount}'


class GlobalPoolMember(models.Model):
    class StatusChoices(models.TextChoices):
        ACTIVE = 'active', 'Active'
        EXITED = 'exited', 'Exited'

    id = models.AutoField(primary_key=True)
    user_profile = models.OneToOneField(UserProfile, on_delete=models.CASCADE, related_name='global_pool_member')
    qualified_at = models.DateTimeField()
    qualified_by_direct_referrals_count = models.PositiveIntegerField(default=0)
    current_plan = models.ForeignKey(
        SubscriptionMasterPlan,
        on_delete=models.SET_NULL,
        related_name='global_pool_members',
        blank=True,
        null=True,
    )
    max_pool_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_pool_earned = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=StatusChoices.choices, default=StatusChoices.ACTIVE)
    last_reactivated_at = models.DateTimeField(blank=True, null=True)
    exited_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'global_pool_members'
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['status', 'updated_at']),
        ]

    @property
    def remaining_pool_capacity(self):
        remaining = self.max_pool_limit - self.total_pool_earned
        return remaining if remaining > 0 else 0

    def __str__(self):
        return f'{self.user_profile_id} global pool'


class GlobalPoolEvent(models.Model):
    class TriggerType(models.TextChoices):
        NEW_POOL_MEMBER = 'new_pool_member', 'New Pool Member'
        RECHARGE = 'recharge', 'Recharge'
        UPGRADE = 'upgrade', 'Upgrade'

    id = models.AutoField(primary_key=True)
    trigger_type = models.CharField(max_length=30, choices=TriggerType.choices)
    trigger_user_profile = models.ForeignKey(
        UserProfile,
        on_delete=models.SET_NULL,
        related_name='triggered_global_pool_events',
        blank=True,
        null=True,
    )
    membership_reference = models.CharField(max_length=120, blank=True)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    membership_percentage = models.DecimalField(max_digits=6, decimal_places=3, default=0)
    membership_pool_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    business_net_profit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_distribution_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    distributed_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    undistributed_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    idempotency_key = models.CharField(max_length=180, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'global_pool_events'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['trigger_type', 'created_at']),
            models.Index(fields=['membership_reference']),
        ]

    def __str__(self):
        return f'{self.trigger_type} Rs. {self.total_distribution_amount}'


class GlobalPoolDistribution(models.Model):
    id = models.AutoField(primary_key=True)
    event = models.ForeignKey(GlobalPoolEvent, on_delete=models.CASCADE, related_name='distributions')
    receiver = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='global_pool_distributions')
    calculated_share = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    actual_credited = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    remaining_limit_before = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    remaining_limit_after = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'global_pool_distributions'
        constraints = [
            models.UniqueConstraint(fields=['event', 'receiver'], name='unique_global_pool_event_receiver'),
        ]
        indexes = [
            models.Index(fields=['receiver', 'created_at']),
        ]

    def __str__(self):
        return f'{self.receiver_id} Rs. {self.actual_credited}'
