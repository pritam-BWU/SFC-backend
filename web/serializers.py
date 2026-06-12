from django.contrib.auth import authenticate, get_user_model, password_validation
from django.db import transaction
from rest_framework.authtoken.models import Token
from rest_framework import serializers

from .models import (
    IssueReport,
    IssueReportDocument,
    LoyaltyRewardLedger,
    PaymentOrder,
    PaymentRefund,
    PaymentTransaction,
    RewardLedger,
    RewardPoints,
    SubscriptionMasterPlan,
    SubscriptionStatusMaster,
    UserLoyaltyAccount,
    UserNotification,
    UserProfile,
)


User = get_user_model()


def find_mobile_user(login_id):
    normalized_login = login_id.strip().lower()
    normalized_phone = MobileSignupSerializer.normalize_phone(normalized_login)

    user = (
        User.objects.filter(username__iexact=normalized_login).first()
        or User.objects.filter(email__iexact=normalized_login).first()
        or User.objects.filter(username__iexact=normalized_phone).first()
    )

    if not user:
        profile = UserProfile.objects.select_related('user').filter(
            email_address__iexact=normalized_login,
        ).first()
        user = profile.user if profile else None
    if not user:
        profile = UserProfile.objects.select_related('user').filter(
            phone_number__iexact=normalized_phone,
        ).first()
        user = profile.user if profile else None

    return user


class MobileSignupSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    full_name = serializers.CharField(max_length=150)
    dob = serializers.DateField(required=False, allow_null=True)
    pan_no = serializers.CharField(max_length=20, required=False, allow_blank=True)
    gender = serializers.ChoiceField(
        choices=UserProfile.GenderChoices.choices,
        required=False,
        allow_blank=True,
    )
    nationality = serializers.CharField(max_length=80, required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)
    city = serializers.CharField(max_length=80, required=False, allow_blank=True)
    state = serializers.CharField(max_length=80, required=False, allow_blank=True)
    postal_code = serializers.CharField(max_length=20, required=False, allow_blank=True)
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    email_address = serializers.EmailField(required=False, allow_blank=True)
    nominee_full_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    nominee_relationship = serializers.CharField(max_length=80, required=False, allow_blank=True)
    nominee_phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    how_did_you_hear_about_club = serializers.CharField(max_length=150, required=False, allow_blank=True)
    payment_details = serializers.CharField(required=False, allow_blank=True)
    uploaded_form_document = serializers.ImageField(required=False, allow_null=True)
    subscription_plan_id = serializers.PrimaryKeyRelatedField(
        source='subscription_plan',
        queryset=SubscriptionMasterPlan.objects.all(),
        required=False,
        allow_null=True,
    )
    subscription_status_id = serializers.PrimaryKeyRelatedField(
        source='subscription_status',
        queryset=SubscriptionStatusMaster.objects.all(),
        required=False,
        allow_null=True,
    )
    referral_code = serializers.CharField(max_length=30, required=False, allow_blank=True, write_only=True)
    is_active = serializers.BooleanField(required=False, default=True)

    @staticmethod
    def normalize_phone(value):
        return ''.join(char for char in value.strip() if char.isdigit() or char == '+')

    def validate_email_address(self, value):
        normalized_email = value.strip().lower()
        if not normalized_email:
            return ''
        if User.objects.filter(email__iexact=normalized_email).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        if UserProfile.objects.filter(email_address__iexact=normalized_email).exists():
            raise serializers.ValidationError('A profile with this email already exists.')
        return normalized_email

    def validate_phone_number(self, value):
        normalized_phone = self.normalize_phone(value)
        if not normalized_phone:
            return ''
        if User.objects.filter(username__iexact=normalized_phone).exists():
            raise serializers.ValidationError('A user with this phone number already exists.')
        if UserProfile.objects.filter(phone_number__iexact=normalized_phone).exists():
            raise serializers.ValidationError('A profile with this phone number already exists.')
        return normalized_phone

    def validate_username(self, value):
        username = value.strip().lower()
        if username and User.objects.filter(username__iexact=username).exists():
            raise serializers.ValidationError('A user with this username already exists.')
        return username

    def validate(self, attrs):
        email = attrs.get('email_address', '').strip().lower()
        phone = attrs.get('phone_number', '').strip()
        requested_username = attrs.get('username', '').strip().lower()
        username = email or phone or requested_username

        if not username:
            raise serializers.ValidationError({'login_id': 'Email or phone number is required.'})
        if User.objects.filter(username__iexact=username).exists():
            raise serializers.ValidationError({'login_id': 'A user with this email or phone number already exists.'})

        attrs['username'] = username
        attrs['email_address'] = email
        attrs['phone_number'] = phone
        referral_code = attrs.pop('referral_code', '').strip().upper()
        if referral_code:
            referrer = UserProfile.objects.filter(referral_code__iexact=referral_code, is_active=True).first()
            if not referrer:
                raise serializers.ValidationError({'referral_code': 'Invalid referral code.'})
            attrs['referred_by'] = referrer
        password_validation.validate_password(attrs['password'])
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop('password')
        username = validated_data.pop('username')
        email = validated_data.get('email_address', '')
        full_name = validated_data.get('full_name', username)

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=full_name.split(' ', 1)[0],
            last_name=full_name.split(' ', 1)[1] if ' ' in full_name else '',
        )
        profile = UserProfile.objects.create(
            user=user,
            ip_address=self.context.get('ip_address'),
            **validated_data,
        )
        if profile.referred_by_id:
            from .reward_engine import ensure_referral_edge

            ensure_referral_edge(profile)
        return profile


class MobileLoginSerializer(serializers.Serializer):
    login_id = serializers.CharField(required=False, allow_blank=True)
    email = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        login_id = (attrs.get('login_id') or attrs.get('email') or '').strip().lower()
        password = attrs['password']
        if not login_id:
            raise serializers.ValidationError('Email or phone number is required.')
        user = find_mobile_user(login_id)

        if not user:
            raise serializers.ValidationError('Invalid email/phone or password.')

        authenticated_user = authenticate(username=user.username, password=password)
        if not authenticated_user:
            raise serializers.ValidationError('Invalid email/phone or password.')
        if not authenticated_user.is_active:
            raise serializers.ValidationError('This account is inactive.')

        profile = UserProfile.objects.filter(user=authenticated_user, is_active=True).first()
        if not profile:
            raise serializers.ValidationError('No active profile found for this account.')

        attrs['user'] = authenticated_user
        attrs['profile'] = profile
        attrs['token'], _ = Token.objects.get_or_create(user=authenticated_user)
        return attrs


class MobilePasswordChangeSerializer(serializers.Serializer):
    login_id = serializers.CharField()
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)
    confirm_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        login_id = attrs['login_id'].strip().lower()
        if not login_id:
            raise serializers.ValidationError({'login_id': 'Email or phone number is required.'})

        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match.'})

        user = find_mobile_user(login_id)
        if not user:
            raise serializers.ValidationError({'login_id': 'No account found with this email or phone number.'})
        if not user.is_active:
            raise serializers.ValidationError({'login_id': 'This account is inactive.'})

        password_validation.validate_password(attrs['new_password'], user)
        attrs['user'] = user
        return attrs

    @transaction.atomic
    def save(self, **kwargs):
        user = self.validated_data['user']
        user.set_password(self.validated_data['new_password'])
        user.save(update_fields=['password'])
        Token.objects.filter(user=user).delete()
        return user


class UserNotificationSerializer(serializers.ModelSerializer):
    event_key = serializers.CharField(source='event.event_key', read_only=True)

    class Meta:
        model = UserNotification
        fields = (
            'id',
            'event_key',
            'title',
            'message',
            'deep_link',
            'metadata',
            'is_read',
            'read_at',
            'created_at',
        )


class IssueReportDocumentSerializer(serializers.ModelSerializer):
    url = serializers.CharField(source='file_url', read_only=True)

    class Meta:
        model = IssueReportDocument
        fields = (
            'id',
            'url',
            'original_name',
            'uploaded_at',
        )


class IssueReportSerializer(serializers.ModelSerializer):
    attachments = IssueReportDocumentSerializer(source='documents', many=True, read_only=True)

    class Meta:
        model = IssueReport
        fields = (
            'report_id',
            'description',
            'status',
            'attachments',
            'created_at',
            'updated_at',
        )


class IssueReportCreateSerializer(serializers.Serializer):
    description = serializers.CharField(trim_whitespace=True, min_length=10)

    def validate_description(self, value):
        if not value:
            raise serializers.ValidationError('Description is required.')
        return value


class PaymentOrderCreateSerializer(serializers.Serializer):
    subscription_plan_id = serializers.PrimaryKeyRelatedField(
        source='subscription_plan',
        queryset=SubscriptionMasterPlan.objects.all(),
    )


class PaymentOrderSerializer(serializers.ModelSerializer):
    subscription_plan_name = serializers.CharField(source='subscription_plan.plan_name', read_only=True)
    provider_name = serializers.CharField(source='provider.provider_name', read_only=True)

    class Meta:
        model = PaymentOrder
        fields = (
            'id',
            'receipt',
            'gateway_order_id',
            'subscription_plan',
            'subscription_plan_name',
            'provider_name',
            'amount',
            'currency',
            'status',
            'paid_at',
            'created_at',
            'updated_at',
        )


class PaymentConfirmSerializer(serializers.Serializer):
    payment_order_id = serializers.PrimaryKeyRelatedField(
        source='payment_order',
        queryset=PaymentOrder.objects.all(),
    )
    razorpay_payment_id = serializers.CharField(max_length=120)
    razorpay_order_id = serializers.CharField(max_length=120, required=False, allow_blank=True)
    razorpay_signature = serializers.CharField(max_length=255, required=False, allow_blank=True)
    raw_payload = serializers.JSONField(required=False)

    def validate(self, attrs):
        request = self.context['request']
        order = attrs['payment_order']

        if order.user_profile.user_id != request.user.id:
            raise serializers.ValidationError('This payment order does not belong to the logged-in user.')

        if attrs.get('razorpay_order_id') and not order.gateway_order_id:
            order.gateway_order_id = attrs['razorpay_order_id']
            order.save(update_fields=['gateway_order_id', 'updated_at'])

        return attrs


class PaymentTransactionSerializer(serializers.ModelSerializer):
    receipt = serializers.CharField(source='payment_order.receipt', read_only=True)

    class Meta:
        model = PaymentTransaction
        fields = (
            'id',
            'receipt',
            'gateway_payment_id',
            'amount',
            'currency',
            'status',
            'payment_method',
            'gateway_status',
            'paid_at',
            'created_at',
        )


class PaymentRefundSerializer(serializers.ModelSerializer):
    receipt = serializers.CharField(source='payment_order.receipt', read_only=True)

    class Meta:
        model = PaymentRefund
        fields = (
            'id',
            'receipt',
            'gateway_refund_id',
            'amount',
            'currency',
            'reason',
            'status',
            'requested_at',
            'processed_at',
        )


class LoyaltyPreferenceSerializer(serializers.Serializer):
    loyalty_reward_preference = serializers.ChoiceField(
        choices=UserProfile.LoyaltyRewardPreference.choices,
    )


class UserLoyaltyAccountSerializer(serializers.ModelSerializer):
    member_id = serializers.CharField(source='user_profile_id', read_only=True)

    class Meta:
        model = UserLoyaltyAccount
        fields = (
            'member_id',
            'balance',
            'lifetime_earned',
            'lifetime_redeemed',
            'last_monthly_credit_at',
            'last_yearly_credit_at',
            'created_at',
            'updated_at',
        )


class RewardPointsSerializer(serializers.ModelSerializer):
    member_id = serializers.CharField(source='user_profile_id', read_only=True)
    total_rewards = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = RewardPoints
        fields = (
            'id',
            'member_id',
            'loyalty_reward',
            'referral_rewards',
            'global_pool_rewards',
            'total_rewards',
            'created_at',
            'updated_at',
        )


class RewardLedgerSerializer(serializers.ModelSerializer):
    reward_type_label = serializers.CharField(source='get_reward_type_display', read_only=True)
    subscription_plan_name = serializers.CharField(source='subscription_plan.plan_name', read_only=True)

    class Meta:
        model = RewardLedger
        fields = (
            'id',
            'reward_type',
            'reward_type_label',
            'reward_subtype',
            'level',
            'percentage_used',
            'base_amount',
            'calculated_amount',
            'credited_amount',
            'balance_after',
            'reference_id',
            'note',
            'subscription_plan_name',
            'created_at',
        )


class LoyaltyRewardLedgerSerializer(serializers.ModelSerializer):
    reward_preference_label = serializers.CharField(source='get_reward_preference_display', read_only=True)
    subscription_plan_name = serializers.CharField(source='subscription_plan.plan_name', read_only=True)

    class Meta:
        model = LoyaltyRewardLedger
        fields = (
            'id',
            'entry_type',
            'reward_preference',
            'reward_preference_label',
            'subscription_plan_name',
            'amount',
            'balance_after',
            'period_key',
            'reference_id',
            'source',
            'note',
            'created_at',
        )
