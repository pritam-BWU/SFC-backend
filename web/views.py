import os

from django.contrib.auth.views import LoginView, LogoutView
from django.contrib import messages
from django.conf import settings
from django.core.files.storage import default_storage
from django.http import JsonResponse
from django.utils import timezone
from django.utils.text import get_valid_filename
from django.urls import reverse, reverse_lazy
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import Count, Sum
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework.views import APIView

from .forms import (
    AdminDashboardLoginForm,
    AdminProfileCompletionForm,
    DashboardLoginForm,
    GlobalPoolSettingForm,
    NotificationRuleForm,
    SubscriptionPlanForm,
)
from .models import (
    AdminAccount,
    GlobalPoolEvent,
    GlobalPoolMember,
    GlobalPoolSetting,
    IssueReport,
    IssueReportDocument,
    LoyaltyRewardLedger,
    NotificationEventMaster,
    NotificationRule,
    PaymentOrder,
    PaymentRefund,
    PaymentTransaction,
    ReferralEdge,
    RewardLedger,
    RewardPoints,
    SubscriptionMasterPlan,
    SubscriptionStatusMaster,
    UserLoyaltyAccount,
    UserNotification,
    UserProfile,
)
from .loyalty import (
    can_change_loyalty_preference,
    get_loyalty_account,
    get_preference_label,
    get_reward_points,
    is_loyalty_eligible,
    select_loyalty_preference,
)
from .notifications import create_notification_for_event
from .payments import confirm_payment, create_payment_order, get_razorpay_provider, request_refund, store_webhook_event
from .reward_engine import process_approved_membership
from .serializers import (
    IssueReportCreateSerializer,
    IssueReportSerializer,
    LoyaltyPreferenceSerializer,
    LoyaltyRewardLedgerSerializer,
    MobileLoginSerializer,
    MobilePasswordChangeSerializer,
    MobileSignupSerializer,
    PaymentConfirmSerializer,
    PaymentOrderCreateSerializer,
    PaymentOrderSerializer,
    PaymentRefundSerializer,
    PaymentTransactionSerializer,
    RewardLedgerSerializer,
    RewardPointsSerializer,
    UserLoyaltyAccountSerializer,
    UserNotificationSerializer,
)


ALLOWED_REPORT_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png', 'doc', 'docx', 'xlsx', 'txt'}
MAX_REPORT_DOCUMENTS = 10
MAX_REPORT_DOCUMENT_SIZE = 25 * 1024 * 1024


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def build_mobile_auth_response(profile, token, message):
    user = profile.user
    return {
        'message': message,
        'token': token.key,
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
        },
        'profile': {
            'id': profile.id,
            'full_name': profile.full_name,
            'email_address': profile.email_address or user.email,
            'phone_number': profile.phone_number,
            'gender': profile.gender,
            'subscription_plan_id': profile.subscription_plan_id,
            'referral_code': profile.referral_code,
            'referred_by': profile.referred_by_id,
            'subscription_status_id': profile.subscription_status_id,
            'subscription_status': (
                profile.subscription_status.status_name
                if profile.subscription_status
                else ''
            ),
            'is_active': profile.is_active,
        },
    }


def get_or_create_profile(user):
    profile, _ = UserProfile.objects.select_related('subscription_plan', 'subscription_status').get_or_create(
        user=user,
        defaults={
            'full_name': user.get_full_name() or user.username,
            'email_address': user.email,
        },
    )
    return profile


def get_serializer_error_message(errors):
    if isinstance(errors, dict):
        for value in errors.values():
            return get_serializer_error_message(value)
    if isinstance(errors, list) and errors:
        return get_serializer_error_message(errors[0])
    return str(errors) if errors else 'Invalid request.'


def get_request_user_profile(request):
    return UserProfile.objects.filter(user=request.user, is_active=True).first()


def get_report_files(request):
    return request.FILES.getlist('files[]') or request.FILES.getlist('files')


def validate_report_file(uploaded_file):
    original_name = uploaded_file.name or ''
    extension = original_name.rsplit('.', 1)[-1].lower() if '.' in original_name else ''

    if extension not in ALLOWED_REPORT_EXTENSIONS:
        return 'Unsupported file type'
    if uploaded_file.size > MAX_REPORT_DOCUMENT_SIZE:
        return 'File size cannot exceed 25MB'
    return ''


def home(request):
    return render(request, 'static_pages/home.html')

def membership(request):
    return render(request, 'static_pages/membership.html')

def plan_checkout(request):
    return render(request, 'static_pages/plan_checkout.html')


class DashboardLoginView(LoginView):
    template_name = 'user_dashboard/login.html'
    authentication_form = DashboardLoginForm
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse('dashboard_home')


class DashboardLogoutView(LogoutView):
    next_page = reverse_lazy('dashboard_login')


class DashboardHomeView(LoginRequiredMixin, TemplateView):
    template_name = 'user_dashboard/dashboard.html'
    login_url = reverse_lazy('dashboard_login')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile = get_or_create_profile(self.request.user)
        context['profile'] = profile
        context['reward_points'] = RewardPoints.objects.filter(user_profile=profile).first()
        context['reward_ledger_entries'] = profile.reward_ledger_entries.select_related('source_user_profile', 'subscription_plan').order_by('-created_at')[:20]
        context['global_pool_member'] = getattr(profile, 'global_pool_member', None)
        return context


class UserProfileView(LoginRequiredMixin, TemplateView):
    template_name = 'user_dashboard/profile.html'
    login_url = reverse_lazy('dashboard_login')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['profile'] = get_or_create_profile(self.request.user)
        return context


class UserSubscriptionView(LoginRequiredMixin, TemplateView):
    template_name = 'user_dashboard/subscription.html'
    login_url = reverse_lazy('dashboard_login')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile = get_or_create_profile(self.request.user)
        context['profile'] = profile
        context['subscription_plan'] = profile.subscription_plan
        return context


class MobileSignupAPIView(APIView):
    permission_classes = [AllowAny]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def post(self, request, *args, **kwargs):
        serializer = MobileSignupSerializer(
            data=request.data,
            context={'ip_address': get_client_ip(request)},
        )
        serializer.is_valid(raise_exception=True)
        profile = serializer.save()
        create_notification_for_event(profile, 'user_registered')
        if profile.subscription_plan:
            create_notification_for_event(profile, 'subscription_pending_review')
        token, _ = Token.objects.get_or_create(user=profile.user)
        return Response(
            build_mobile_auth_response(profile, token, 'Signup completed successfully.'),
            status=status.HTTP_201_CREATED,
        )


class MobileLoginAPIView(APIView):
    permission_classes = [AllowAny]
    parser_classes = [JSONParser, FormParser]

    def post(self, request, *args, **kwargs):
        serializer = MobileLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            build_mobile_auth_response(
                serializer.validated_data['profile'],
                serializer.validated_data['token'],
                'Login successful.',
            )
        )


class MobilePasswordChangeAPIView(APIView):
    permission_classes = [AllowAny]
    parser_classes = [JSONParser, FormParser]

    def post(self, request, *args, **kwargs):
        serializer = MobilePasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({'message': 'Password updated successfully.'})


class MobileIssueReportAPIView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def get(self, request, *args, **kwargs):
        profile = get_request_user_profile(request)
        if not profile:
            return Response({'message': 'User profile not found.'}, status=status.HTTP_404_NOT_FOUND)

        reports = profile.issue_reports.prefetch_related('documents').order_by('-created_at')
        serializer = IssueReportSerializer(reports, many=True)
        return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        profile = get_request_user_profile(request)
        if not profile:
            return Response({'message': 'User profile not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = IssueReportCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'message': get_serializer_error_message(serializer.errors)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        report = IssueReport.objects.create(
            user_profile=profile,
            description=serializer.validated_data['description'],
        )
        return Response(
            {
                'success': True,
                'report_id': report.report_id,
            },
            status=status.HTTP_201_CREATED,
        )


class MobileIssueReportDocumentAPIView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, report_id, *args, **kwargs):
        profile = get_request_user_profile(request)
        if not profile:
            return Response({'message': 'User profile not found.'}, status=status.HTTP_404_NOT_FOUND)

        issue_report = get_object_or_404(
            IssueReport,
            report_id=report_id,
            user_profile=profile,
        )
        files = get_report_files(request)

        if not files:
            return Response({'message': 'No files were uploaded.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(files) > MAX_REPORT_DOCUMENTS:
            return Response({'message': 'Maximum 10 files can be uploaded.'}, status=status.HTTP_400_BAD_REQUEST)

        for uploaded_file in files:
            error_message = validate_report_file(uploaded_file)
            if error_message:
                return Response({'message': error_message}, status=status.HTTP_400_BAD_REQUEST)

        today = timezone.localdate().isoformat()
        base_path = f'uploaded_documents/reports/{profile.id}/{today}'
        uploaded_documents = []

        for uploaded_file in files:
            original_name = uploaded_file.name or 'document'
            valid_name = get_valid_filename(os.path.basename(original_name)) or 'document'
            saved_path = default_storage.save(f'{base_path}/{valid_name}', uploaded_file)
            file_url = f'{settings.MEDIA_URL.lstrip("/")}{saved_path}'
            document = IssueReportDocument.objects.create(
                issue_report=issue_report,
                file_url=file_url,
                original_name=original_name[:255],
            )
            uploaded_documents.append(
                {
                    'id': str(document.id),
                    'url': document.file_url,
                    'original_name': document.original_name,
                }
            )

        return Response(
            {
                'uploaded': True,
                'files': uploaded_documents,
            },
            status=status.HTTP_201_CREATED,
        )


class MobileNotificationListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        profile = get_object_or_404(UserProfile, user=request.user)
        notifications = profile.notifications.select_related('event').order_by('-created_at')

        if request.query_params.get('unread') == '1':
            notifications = notifications.filter(is_read=False)

        serializer = UserNotificationSerializer(notifications, many=True)
        return Response(serializer.data)


class MobileNotificationReadAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, notification_id, *args, **kwargs):
        profile = get_object_or_404(UserProfile, user=request.user)
        notification = get_object_or_404(
            UserNotification,
            id=notification_id,
            user_profile=profile,
        )
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save(update_fields=['is_read', 'read_at'])
        return Response({'message': 'Notification marked as read.'})


class MobileNotificationReadAllAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        profile = get_object_or_404(UserProfile, user=request.user)
        updated = profile.notifications.filter(is_read=False).update(
            is_read=True,
            read_at=timezone.now(),
        )
        return Response({'message': 'All notifications marked as read.', 'updated': updated})


class MobileLoyaltyPreferenceAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        profile = get_object_or_404(
            UserProfile.objects.select_related('subscription_plan', 'subscription_status'),
            user=request.user,
        )
        account = get_loyalty_account(profile)
        reward_points = get_reward_points(profile)
        preference = profile.loyalty_reward_preference
        return Response({
            'eligible': is_loyalty_eligible(profile),
            'can_change_preference': can_change_loyalty_preference(profile),
            'points_id': profile.points_id,
            'loyalty_reward_preference': preference,
            'loyalty_reward_preference_label': get_preference_label(preference),
            'selected_at': profile.loyalty_preference_selected_at,
            'locked_until': profile.loyalty_preference_locked_until,
            'plan': {
                'id': profile.subscription_plan_id,
                'name': profile.subscription_plan.plan_name if profile.subscription_plan else '',
                'monthly_reward': profile.subscription_plan.monthly_reward if profile.subscription_plan else 0,
                'yearly_reward': profile.subscription_plan.yearly_reward if profile.subscription_plan else 0,
            },
            'account': UserLoyaltyAccountSerializer(account).data,
            'rewards': RewardPointsSerializer(reward_points).data,
        })

    def post(self, request, *args, **kwargs):
        profile = get_object_or_404(
            UserProfile.objects.select_related('subscription_plan', 'subscription_status'),
            user=request.user,
        )
        serializer = LoyaltyPreferenceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            select_loyalty_preference(
                profile,
                int(serializer.validated_data['loyalty_reward_preference']),
            )
        except ValueError as error:
            return Response({'detail': str(error)}, status=status.HTTP_400_BAD_REQUEST)

        account = get_loyalty_account(profile)
        reward_points = get_reward_points(profile)
        return Response({
            'message': 'Loyalty reward preference saved successfully.',
            'points_id': profile.points_id,
            'loyalty_reward_preference': profile.loyalty_reward_preference,
            'loyalty_reward_preference_label': get_preference_label(profile.loyalty_reward_preference),
            'locked_until': profile.loyalty_preference_locked_until,
            'account': UserLoyaltyAccountSerializer(account).data,
            'rewards': RewardPointsSerializer(reward_points).data,
        })


class MobileLoyaltyHistoryAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        profile = get_object_or_404(UserProfile, user=request.user)
        account = get_loyalty_account(profile)
        reward_points = get_reward_points(profile)
        entries = profile.loyalty_ledger_entries.select_related('subscription_plan').order_by('-created_at')
        return Response({
            'points_id': profile.points_id,
            'account': UserLoyaltyAccountSerializer(account).data,
            'rewards': RewardPointsSerializer(reward_points).data,
            'ledger': LoyaltyRewardLedgerSerializer(entries, many=True).data,
        })


class MobileRewardSummaryAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        profile = get_object_or_404(UserProfile, user=request.user)
        reward_points, _ = RewardPoints.objects.get_or_create(user_profile=profile)
        if profile.points_id != reward_points.id:
            profile.points = reward_points
            profile.save(update_fields=['points', 'updated_at'])

        pool_member = getattr(profile, 'global_pool_member', None)
        entries = profile.reward_ledger_entries.select_related('subscription_plan').order_by('-created_at')[:100]
        return Response({
            'referral_code': profile.referral_code,
            'referred_by': profile.referred_by_id,
            'rewards': RewardPointsSerializer(reward_points).data,
            'global_pool': {
                'qualified': bool(pool_member),
                'status': pool_member.status if pool_member else '',
                'max_pool_limit': pool_member.max_pool_limit if pool_member else 0,
                'total_pool_earned': pool_member.total_pool_earned if pool_member else 0,
                'remaining_pool_capacity': pool_member.remaining_pool_capacity if pool_member else 0,
            },
            'ledger': RewardLedgerSerializer(entries, many=True).data,
        })


class MobilePaymentOrderCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        profile = get_object_or_404(UserProfile, user=request.user)
        serializer = PaymentOrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = create_payment_order(
            profile=profile,
            subscription_plan=serializer.validated_data['subscription_plan'],
            notes={'source': 'mobile_app'},
        )
        return Response({
            'message': 'Payment order created successfully.',
            'order': PaymentOrderSerializer(order).data,
            'razorpay_key_id': settings.RAZORPAY_KEY_ID,
            'amount_in_paise': int(order.amount * 100),
            'gateway_order_id': order.gateway_order_id,
            'receipt': order.receipt,
        }, status=status.HTTP_201_CREATED)


class MobilePaymentConfirmAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = PaymentConfirmSerializer(
            data=request.data,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        order = serializer.validated_data['payment_order']

        try:
            transaction_obj = confirm_payment(
                order=order,
                gateway_payment_id=serializer.validated_data['razorpay_payment_id'],
                gateway_signature=serializer.validated_data.get('razorpay_signature', ''),
                raw_payload=serializer.validated_data.get('raw_payload', request.data),
            )
        except ValueError as error:
            return Response({'detail': str(error)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'message': 'Payment confirmed successfully. Subscription is pending office approval.',
            'order': PaymentOrderSerializer(order).data,
            'transaction': PaymentTransactionSerializer(transaction_obj).data,
        })


class MobilePaymentHistoryAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        profile = get_object_or_404(UserProfile, user=request.user)
        return Response({
            'orders': PaymentOrderSerializer(
                profile.payment_orders.select_related('subscription_plan', 'provider').order_by('-created_at'),
                many=True,
            ).data,
            'transactions': PaymentTransactionSerializer(
                profile.payment_transactions.select_related('payment_order').order_by('-created_at'),
                many=True,
            ).data,
            'refunds': PaymentRefundSerializer(
                profile.payment_refunds.select_related('payment_order').order_by('-created_at'),
                many=True,
            ).data,
        })


class RazorpayWebhookAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        webhook_event = store_webhook_event(
            provider=get_razorpay_provider(),
            raw_body=request.body,
            headers=request.headers,
        )
        return Response({
            'message': 'Webhook stored successfully.',
            'event_id': webhook_event.id,
            'is_valid_signature': webhook_event.is_valid_signature,
        }, status=status.HTTP_202_ACCEPTED)


def admin_dashboard_required(view_func):
    def wrapper(request, *args, **kwargs):
        admin_id = request.session.get('club_admin_id')
        if not admin_id:
            return redirect('admin_dashboard_login')

        try:
            request.club_admin = AdminAccount.objects.get(id=admin_id, is_active=True)
        except AdminAccount.DoesNotExist:
            request.session.pop('club_admin_id', None)
            return redirect('admin_dashboard_login')

        return view_func(request, *args, **kwargs)

    return wrapper


def get_admin_dashboard_context(request, active_page):
    profiles = UserProfile.objects.select_related('subscription_plan', 'subscription_status', 'user')
    total_users = profiles.count()
    active_users = profiles.filter(is_active=True).count()
    plan_counts = profiles.values('subscription_plan__plan_name').annotate(total=Count('id'))
    pending_status = SubscriptionStatusMaster.objects.filter(status_name='pending').first()

    return {
        'active_page': active_page,
        'club_admin': getattr(request, 'club_admin', None),
        'total_users': total_users,
        'active_users': active_users,
        'pending_approvals': profiles.filter(subscription_status=pending_status).count() if pending_status else 0,
        'pending_payments': profiles.filter(payment_details='').count(),
        'flexible_members': profiles.filter(subscription_plan__refundable=True).count(),
        'long_duration_members': profiles.filter(subscription_plan__non_refundable=True).count(),
        'plan_counts': plan_counts,
        'recent_profiles': profiles.order_by('-created_at')[:5],
    }


def get_membership_requests():
    pending_status = SubscriptionStatusMaster.objects.filter(status_name='pending').first()
    profiles = UserProfile.objects.select_related(
        'subscription_plan',
        'subscription_status',
        'user',
    ).order_by('-created_at')

    if pending_status:
        profiles = profiles.filter(subscription_status=pending_status)

    return profiles


def set_profile_subscription_status(profile, status_name):
    status_obj = get_object_or_404(SubscriptionStatusMaster, status_name=status_name)
    profile.subscription_status = status_obj
    profile.save(update_fields=['subscription_status', 'updated_at'])


def get_support_tickets():
    return [
        {'ticket_id': 'TKT2543', 'name': 'Rahul Sharma', 'subject': 'Payment issue', 'priority': 'High', 'status': 'Open', 'created_on': '31 May 2026'},
        {'ticket_id': 'TKT2542', 'name': 'Priya Singh', 'subject': 'Membership request', 'priority': 'Medium', 'status': 'In Progress', 'created_on': '31 May 2026'},
        {'ticket_id': 'TKT2541', 'name': 'Anita Verma', 'subject': 'Profile update', 'priority': 'Low', 'status': 'Resolved', 'created_on': '30 May 2026'},
        {'ticket_id': 'TKT2540', 'name': 'Suresh Jain', 'subject': 'App login issue', 'priority': 'High', 'status': 'Open', 'created_on': '29 May 2026'},
    ]


def admin_dashboard_login(request):
    if request.session.get('club_admin_id'):
        return redirect('admin_dashboard_home')

    form = AdminDashboardLoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        request.session['club_admin_id'] = form.cleaned_data['admin_account'].id
        return redirect('admin_dashboard_home')

    return render(request, 'admin_dashboard/login.html', {'form': form})


def admin_dashboard_logout(request):
    request.session.pop('club_admin_id', None)
    messages.success(request, 'Admin logged out successfully.')
    return redirect('admin_dashboard_login')


@admin_dashboard_required
def admin_dashboard_home(request):
    context = get_admin_dashboard_context(request, 'dashboard')
    return render(request, 'admin_dashboard/dashboard.html', context)


@admin_dashboard_required
def admin_registered_users(request):
    context = get_admin_dashboard_context(request, 'registered_users')
    context['profiles'] = UserProfile.objects.select_related('subscription_plan', 'subscription_status', 'user').order_by('-created_at')
    return render(request, 'admin_dashboard/registered_users.html', context)


@admin_dashboard_required
def admin_user_details(request, profile_id):
    context = get_admin_dashboard_context(request, 'registered_users')
    context['profile'] = get_object_or_404(
        UserProfile.objects.select_related('subscription_plan', 'subscription_status', 'user'),
        pk=profile_id,
    )
    return render(request, 'admin_dashboard/user_details.html', context)


@admin_dashboard_required
def admin_membership_dashboard(request):
    context = get_admin_dashboard_context(request, 'membership_dashboard')
    context['profiles'] = UserProfile.objects.select_related('subscription_plan', 'subscription_status', 'user').order_by('-created_at')[:8]
    return render(request, 'admin_dashboard/membership_dashboard.html', context)


@admin_dashboard_required
def admin_subscription_plans(request, plan_id=None):
    context = get_admin_dashboard_context(request, 'subscription_plans')
    plan = None

    if plan_id:
        plan = get_object_or_404(SubscriptionMasterPlan, pk=plan_id)

    form = SubscriptionPlanForm(request.POST or None, instance=plan)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if request.method == 'POST' and form.is_valid():
        saved_plan = form.save()
        success_message = 'Subscription plan updated successfully.' if plan else 'Subscription plan created successfully.'

        if is_ajax:
            return JsonResponse({
                'success': True,
                'message': success_message,
                'plan': {
                    'id': saved_plan.id,
                    'plan_name': saved_plan.plan_name,
                    'plan_price': str(saved_plan.plan_price),
                'monthly_reward': str(saved_plan.monthly_reward),
                'yearly_reward': str(saved_plan.yearly_reward),
                'global_pool_limit': str(saved_plan.global_pool_limit),
                'refundable': saved_plan.refundable,
                'non_refundable': saved_plan.non_refundable,
                'created_at': saved_plan.created_at.strftime('%d %b %Y'),
                    'edit_url': reverse('admin_subscription_plan_edit', args=[saved_plan.id]),
                },
            })
        messages.success(request, success_message)
        return redirect('admin_subscription_plans')

    if request.method == 'POST' and is_ajax:
        return JsonResponse({
            'success': False,
            'errors': {
                field: [str(error) for error in errors]
                for field, errors in form.errors.items()
            },
        }, status=400)

    context['form'] = form
    context['editing_plan'] = plan
    context['plans'] = SubscriptionMasterPlan.objects.order_by('plan_price', 'plan_name')
    return render(request, 'admin_dashboard/subscription_plans.html', context)


@admin_dashboard_required
def admin_payments_dashboard(request):
    context = get_admin_dashboard_context(request, 'payments')
    orders = PaymentOrder.objects.select_related('user_profile', 'subscription_plan', 'provider').order_by('-created_at')
    transactions = PaymentTransaction.objects.select_related('payment_order', 'user_profile').order_by('-created_at')
    refunds = PaymentRefund.objects.select_related('payment_order', 'user_profile').order_by('-created_at')

    paid_orders = orders.filter(status=PaymentOrder.StatusChoices.PAID)
    refund_records = refunds.filter(
        status__in=[
            PaymentRefund.StatusChoices.REQUESTED,
            PaymentRefund.StatusChoices.PROCESSED,
        ]
    )
    gross_collection = paid_orders.aggregate(total=Sum('amount'))['total'] or 0
    refund_total = refund_records.aggregate(total=Sum('amount'))['total'] or 0

    context.update({
        'orders': orders[:25],
        'transactions': transactions[:15],
        'refunds': refunds[:15],
        'total_orders': orders.count(),
        'paid_orders': paid_orders.count(),
        'pending_orders': orders.filter(
            status__in=[
                PaymentOrder.StatusChoices.CREATED,
                PaymentOrder.StatusChoices.ATTEMPTED,
            ]
        ).count(),
        'failed_orders': orders.filter(status=PaymentOrder.StatusChoices.FAILED).count(),
        'refunded_orders': orders.filter(status=PaymentOrder.StatusChoices.REFUNDED).count(),
        'gross_collection': gross_collection,
        'refund_total': refund_total,
        'net_collection': gross_collection - refund_total,
    })
    return render(request, 'admin_dashboard/payments.html', context)


@admin_dashboard_required
def admin_loyalty_rewards_dashboard(request):
    context = get_admin_dashboard_context(request, 'loyalty_rewards')
    active_setting = GlobalPoolSetting.objects.filter(is_active=True).order_by('-effective_from', '-created_at').first()
    if not active_setting:
        active_setting = GlobalPoolSetting.objects.create(is_active=True)

    global_pool_form = GlobalPoolSettingForm(request.POST or None, instance=active_setting)
    if request.method == 'POST' and request.POST.get('action') == 'save_global_pool_settings':
        if global_pool_form.is_valid():
            setting = global_pool_form.save(commit=False)
            setting.effective_from = timezone.now()
            setting.save()
            messages.success(request, 'Global pool settings saved successfully.')
            return redirect('admin_loyalty_rewards_dashboard')

    reward_points = RewardPoints.objects.select_related(
        'user_profile__user',
        'user_profile__subscription_plan',
        'user_profile__subscription_status',
    ).order_by('-updated_at')
    accounts = UserLoyaltyAccount.objects.select_related(
        'user_profile__user',
        'user_profile__subscription_plan',
        'user_profile__subscription_status',
    ).order_by('-updated_at')
    ledger_entries = LoyaltyRewardLedger.objects.select_related(
        'user_profile__user',
        'subscription_plan',
    ).order_by('-created_at')
    reward_ledger_entries = RewardLedger.objects.select_related(
        'user_profile__user',
        'source_user_profile',
        'subscription_plan',
    ).order_by('-created_at')
    pool_members = GlobalPoolMember.objects.select_related(
        'user_profile__user',
        'current_plan',
    ).order_by('-updated_at')
    pool_events = GlobalPoolEvent.objects.select_related('trigger_user_profile').order_by('-created_at')

    today = timezone.localdate()
    current_month_key = today.strftime('%Y-%m')
    current_year_key = today.strftime('%Y')
    current_period_credits = ledger_entries.filter(
        entry_type=LoyaltyRewardLedger.EntryType.CREDIT,
        period_key__in=[current_month_key, current_year_key],
    )

    context.update({
        'reward_points': reward_points[:50],
        'accounts': accounts[:50],
        'ledger_entries': ledger_entries[:25],
        'reward_ledger_entries': reward_ledger_entries[:50],
        'pool_members': pool_members[:50],
        'pool_events': pool_events[:25],
        'global_pool_form': global_pool_form,
        'global_pool_setting': active_setting,
        'total_accounts': reward_points.count(),
        'active_pool_members': pool_members.filter(status=GlobalPoolMember.StatusChoices.ACTIVE).count(),
        'exited_pool_members': pool_members.filter(status=GlobalPoolMember.StatusChoices.EXITED).count(),
        'completed_direct_referrals': ReferralEdge.objects.filter(status=ReferralEdge.StatusChoices.COMPLETED).count(),
        'monthly_preferences': UserProfile.objects.filter(
            loyalty_reward_preference=UserProfile.LoyaltyRewardPreference.MONTHLY,
        ).count(),
        'yearly_preferences': UserProfile.objects.filter(
            loyalty_reward_preference=UserProfile.LoyaltyRewardPreference.YEARLY,
        ).count(),
        'total_loyalty_rewards': reward_points.aggregate(total=Sum('loyalty_reward'))['total'] or 0,
        'total_referral_rewards': reward_points.aggregate(total=Sum('referral_rewards'))['total'] or 0,
        'total_global_pool_rewards': reward_points.aggregate(total=Sum('global_pool_rewards'))['total'] or 0,
        'total_balance': (
            (reward_points.aggregate(total=Sum('loyalty_reward'))['total'] or 0)
            + (reward_points.aggregate(total=Sum('referral_rewards'))['total'] or 0)
            + (reward_points.aggregate(total=Sum('global_pool_rewards'))['total'] or 0)
        ),
        'lifetime_earned': accounts.aggregate(total=Sum('lifetime_earned'))['total'] or 0,
        'current_period_credit_total': current_period_credits.aggregate(total=Sum('amount'))['total'] or 0,
        'current_period_credit_count': current_period_credits.count(),
        'current_month_key': current_month_key,
        'current_year_key': current_year_key,
    })
    return render(request, 'admin_dashboard/loyalty_rewards.html', context)


@admin_dashboard_required
def admin_membership_requests(request):
    context = get_admin_dashboard_context(request, 'membership_requests')
    context['profiles'] = get_membership_requests()
    return render(request, 'admin_dashboard/membership_requests.html', context)


@admin_dashboard_required
def admin_membership_request_details(request, request_id):
    context = get_admin_dashboard_context(request, 'membership_requests')
    profile = get_object_or_404(
        UserProfile.objects.select_related('subscription_plan', 'subscription_status', 'user'),
        pk=request_id,
    )
    form = AdminProfileCompletionForm(
        request.POST or None,
        request.FILES or None,
        instance=profile,
    )

    if request.method == 'POST':
        action = request.POST.get('action')
        status_actions = {
            'approve': 'completed',
            'reject': 'rejected',
            'transfer': 'transfered',
            'close': 'closed',
        }

        if action in status_actions:
            set_profile_subscription_status(profile, status_actions[action])
            event_key = {
                'approve': 'subscription_approved',
                'reject': 'subscription_rejected',
                'transfer': 'subscription_transfered',
                'close': 'subscription_closed',
            }[action]
            if action == 'approve':
                paid_order = profile.payment_orders.filter(
                    status=PaymentOrder.StatusChoices.PAID,
                ).order_by('-paid_at', '-created_at').first()
                process_approved_membership(profile, paid_order=paid_order)
            create_notification_for_event(profile, event_key)
            messages.success(request, f'Subscription marked as {status_actions[action]}.')
            return redirect('admin_membership_request_details', request_id=profile.id)

        if action == 'reject_refund':
            set_profile_subscription_status(profile, 'rejected')
            paid_order = profile.payment_orders.filter(
                status=PaymentOrder.StatusChoices.PAID,
            ).order_by('-paid_at', '-created_at').first()
            if paid_order:
                request_refund(
                    order=paid_order,
                    reason='Subscription rejected by office authority.',
                    requested_by=getattr(request, 'club_admin', None),
                )
                create_notification_for_event(profile, 'subscription_rejected')
                messages.success(request, 'Subscription rejected and refund request recorded.')
            else:
                messages.error(request, 'Subscription rejected, but no paid order was found for refund.')
            return redirect('admin_membership_request_details', request_id=profile.id)

        if action == 'save_profile' and form.is_valid():
            had_document = bool(profile.uploaded_form_document)
            form.save()
            create_notification_for_event(profile, 'profile_completed')
            if request.FILES.get('uploaded_form_document') and not had_document:
                create_notification_for_event(profile, 'physical_form_uploaded')
            messages.success(request, 'Profile details saved from physical form.')
            return redirect('admin_membership_request_details', request_id=profile.id)

    context['profile'] = profile
    context['form'] = form
    return render(request, 'admin_dashboard/membership_request_details.html', context)


@admin_dashboard_required
def admin_send_notification(request):
    context = get_admin_dashboard_context(request, 'send_notification')
    return render(request, 'admin_dashboard/send_notification.html', context)


@admin_dashboard_required
def admin_notification_rules(request):
    context = get_admin_dashboard_context(request, 'notification_rules')
    context['events'] = NotificationEventMaster.objects.order_by('id')
    return render(request, 'admin_dashboard/notification_rules.html', context)


@admin_dashboard_required
def admin_notification_rule_detail(request, event_key):
    context = get_admin_dashboard_context(request, 'notification_rules')
    selected_event = get_object_or_404(NotificationEventMaster, event_key=event_key)
    rule, _ = NotificationRule.objects.get_or_create(
        event=selected_event,
        defaults={
            'title_template': selected_event.event_name,
            'message_template': 'Hello {full_name}, there is an update for your SFC membership.',
        },
    )

    form = NotificationRuleForm(request.POST or None, instance=rule)
    if request.method == 'POST' and form.is_valid():
        notification_rule = form.save(commit=False)
        notification_rule.event = selected_event
        notification_rule.save()
        messages.success(request, 'Notification rule saved successfully.')
        return redirect('admin_notification_rule_detail', event_key=selected_event.event_key)

    context['selected_event'] = selected_event
    context['form'] = form
    context['template_variables'] = [
        'full_name',
        'member_id',
        'username',
        'phone_number',
        'email_address',
        'plan_name',
        'plan_price',
        'subscription_status',
        'city',
        'created_date',
        'reward_frequency',
        'locked_until',
        'reward_amount',
        'reward_period',
        'loyalty_balance',
        'reward_percentage',
        'referral_count',
        'referral_level',
        'referral_role',
        'global_pool_balance',
        'global_pool_limit',
    ]
    return render(request, 'admin_dashboard/notification_rule_detail.html', context)


@admin_dashboard_required
def admin_support_tickets(request):
    context = get_admin_dashboard_context(request, 'support_tickets')
    context['tickets'] = get_support_tickets()
    return render(request, 'admin_dashboard/support_tickets.html', context)


@admin_dashboard_required
def admin_ticket_details(request, ticket_id):
    context = get_admin_dashboard_context(request, 'support_tickets')
    tickets = get_support_tickets()
    context['ticket'] = next((ticket for ticket in tickets if ticket['ticket_id'] == ticket_id), tickets[0])
    return render(request, 'admin_dashboard/ticket_details.html', context)
