import os
import shutil
import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import (
    GlobalPoolMember,
    GlobalPoolSetting,
    IssueReportDocument,
    ReferralEdge,
    RewardLedger,
    RewardPoints,
    SubscriptionMasterPlan,
    SubscriptionStatusMaster,
    UserProfile,
)
from .reward_engine import evaluate_global_pool_for_profile, process_approved_membership


User = get_user_model()


class MobileAuthAPITests(APITestCase):
    def authenticate_mobile_user(self):
        signup_response = self.client.post(
            reverse('mobile_signup'),
            {
                'full_name': 'Issue Reporter',
                'email_address': 'issue.reporter@example.com',
                'gender': 'O',
                'password': 'FreshPass123!',
            },
            format='json',
        )
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {signup_response.data["token"]}')
        return UserProfile.objects.get(email_address='issue.reporter@example.com')

    def test_mobile_signup_creates_profile_without_subscription_status(self):
        response = self.client.post(
            reverse('mobile_signup'),
            {
                'full_name': 'Test User',
                'email_address': 'test.user@example.com',
                'gender': 'O',
                'password': 'FreshPass123!',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('token', response.data)
        profile = UserProfile.objects.get(email_address='test.user@example.com')
        self.assertEqual(profile.full_name, 'Test User')
        self.assertEqual(profile.gender, 'O')
        self.assertIsNone(profile.subscription_status)
        self.assertEqual(response.data['profile']['subscription_status'], '')

    def test_mobile_login_validates_email_and_password(self):
        self.client.post(
            reverse('mobile_signup'),
            {
                'full_name': 'Login User',
                'email_address': 'login.user@example.com',
                'gender': 'F',
                'password': 'FreshPass123!',
            },
            format='json',
        )

        response = self.client.post(
            reverse('mobile_login'),
            {
                'email': 'login.user@example.com',
                'password': 'FreshPass123!',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('token', response.data)
        self.assertEqual(response.data['profile']['email_address'], 'login.user@example.com')

    def test_mobile_signup_and_login_with_phone_number(self):
        signup_response = self.client.post(
            reverse('mobile_signup'),
            {
                'full_name': 'Phone User',
                'phone_number': '9876543210',
                'gender': 'M',
                'password': 'FreshPass123!',
            },
            format='json',
        )

        self.assertEqual(signup_response.status_code, status.HTTP_201_CREATED)
        profile = UserProfile.objects.get(phone_number='9876543210')
        self.assertEqual(profile.email_address, '')
        self.assertEqual(profile.user.username, '9876543210')

        login_response = self.client.post(
            reverse('mobile_login'),
            {
                'login_id': '9876543210',
                'password': 'FreshPass123!',
            },
            format='json',
        )

        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        self.assertIn('token', login_response.data)
        self.assertEqual(login_response.data['profile']['phone_number'], '9876543210')

    def test_mobile_password_change_updates_login_password(self):
        self.client.post(
            reverse('mobile_signup'),
            {
                'full_name': 'Reset User',
                'phone_number': '9123456789',
                'gender': 'M',
                'password': 'FreshPass123!',
            },
            format='json',
        )

        change_response = self.client.post(
            reverse('mobile_change_password'),
            {
                'login_id': '9123456789',
                'new_password': 'UpdatedPass123!',
                'confirm_password': 'UpdatedPass123!',
            },
            format='json',
        )

        self.assertEqual(change_response.status_code, status.HTTP_200_OK)

        old_login_response = self.client.post(
            reverse('mobile_login'),
            {
                'login_id': '9123456789',
                'password': 'FreshPass123!',
            },
            format='json',
        )
        self.assertEqual(old_login_response.status_code, status.HTTP_400_BAD_REQUEST)

        new_login_response = self.client.post(
            reverse('mobile_login'),
            {
                'login_id': '9123456789',
                'password': 'UpdatedPass123!',
            },
            format='json',
        )
        self.assertEqual(new_login_response.status_code, status.HTTP_200_OK)

    def test_mobile_report_issue_create_upload_and_list(self):
        profile = self.authenticate_mobile_user()
        media_root = tempfile.mkdtemp()

        try:
            with self.settings(MEDIA_ROOT=media_root):
                create_response = self.client.post(
                    reverse('mobile_report_issue'),
                    {
                        'description': 'Unable to upload my KYC document from the app.',
                    },
                    format='json',
                )

                self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
                self.assertTrue(create_response.data['success'])
                self.assertRegex(create_response.data['report_id'], r'^RPT-\d{4}-\d{6}$')

                document = SimpleUploadedFile(
                    'issue_file.pdf',
                    b'PDF test content',
                    content_type='application/pdf',
                )
                upload_response = self.client.post(
                    reverse(
                        'mobile_report_issue_documents',
                        kwargs={'report_id': create_response.data['report_id']},
                    ),
                    {
                        'files[]': [document],
                    },
                    format='multipart',
                )

                self.assertEqual(upload_response.status_code, status.HTTP_201_CREATED)
                self.assertTrue(upload_response.data['uploaded'])
                self.assertEqual(len(upload_response.data['files']), 1)
                file_url = upload_response.data['files'][0]['url']
                expected_prefix = f'media/uploaded_documents/reports/{profile.id}/'
                self.assertTrue(file_url.startswith(expected_prefix))
                self.assertTrue(file_url.endswith('/issue_file.pdf'))
                self.assertTrue(os.path.exists(os.path.join(media_root, file_url.removeprefix('media/'))))

                list_response = self.client.get(reverse('mobile_report_issue'))

                self.assertEqual(list_response.status_code, status.HTTP_200_OK)
                self.assertEqual(list_response.data[0]['report_id'], create_response.data['report_id'])
                self.assertEqual(list_response.data[0]['status'], 'OPEN')
                self.assertEqual(list_response.data[0]['attachments'][0]['url'], file_url)
        finally:
            shutil.rmtree(media_root, ignore_errors=True)

    def test_mobile_report_issue_rejects_short_description(self):
        self.authenticate_mobile_user()

        response = self.client.post(
            reverse('mobile_report_issue'),
            {
                'description': 'Too short',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('message', response.data)

    def test_mobile_report_issue_rejects_unsupported_file_type(self):
        self.authenticate_mobile_user()
        report_response = self.client.post(
            reverse('mobile_report_issue'),
            {
                'description': 'This report has an unsupported attachment.',
            },
            format='json',
        )
        unsupported_file = SimpleUploadedFile(
            'malware.exe',
            b'bad file',
            content_type='application/octet-stream',
        )

        response = self.client.post(
            reverse(
                'mobile_report_issue_documents',
                kwargs={'report_id': report_response.data['report_id']},
            ),
            {
                'files[]': [unsupported_file],
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['message'], 'Unsupported file type')
        self.assertEqual(IssueReportDocument.objects.count(), 0)

    def test_user_dashboard_profile_update_does_not_change_nominee_details(self):
        profile = self.authenticate_mobile_user()
        profile.nominee_full_name = 'Admin Nominee'
        profile.nominee_relationship = 'Sibling'
        profile.nominee_phone_number = '9000000000'
        profile.save(update_fields=['nominee_full_name', 'nominee_relationship', 'nominee_phone_number'])
        self.client.force_login(profile.user)

        response = self.client.post(
            reverse('dashboard_profile'),
            {
                'full_name': 'Updated User',
                'dob': '1995-01-15',
                'pan_no': 'ABCDE1234F',
                'gender': 'O',
                'nationality': 'Indian',
                'address': 'Updated address',
                'city': 'Kolkata',
                'state': 'West Bengal',
                'postal_code': '700001',
                'phone_number': '9876500000',
                'email_address': 'updated.user@example.com',
                'how_did_you_hear_about_club': 'Friend',
                'nominee_full_name': 'Tampered Nominee',
            },
        )

        self.assertEqual(response.status_code, 302)
        profile.refresh_from_db()
        self.assertEqual(profile.full_name, 'Updated User')
        self.assertEqual(profile.city, 'Kolkata')
        self.assertEqual(profile.nominee_full_name, 'Admin Nominee')
        self.assertEqual(profile.nominee_relationship, 'Sibling')
        self.assertEqual(profile.nominee_phone_number, '9000000000')


class RewardEngineTests(APITestCase):
    def setUp(self):
        self.completed_status, _ = SubscriptionStatusMaster.objects.get_or_create(status_name='completed')
        self.bronze = SubscriptionMasterPlan.objects.create(
            plan_name='Bronze',
            plan_price=Decimal('5000.00'),
            monthly_reward=Decimal('0.00'),
            yearly_reward=Decimal('0.00'),
            global_pool_limit=Decimal('2999.00'),
        )
        self.silver = SubscriptionMasterPlan.objects.create(
            plan_name='Silver',
            plan_price=Decimal('10000.00'),
            monthly_reward=Decimal('0.00'),
            yearly_reward=Decimal('0.00'),
            global_pool_limit=Decimal('11999.00'),
        )
        GlobalPoolSetting.objects.update_or_create(
            is_active=True,
            defaults={
                'membership_contribution_percentage': Decimal('10.000'),
                'business_net_profit_amount': Decimal('100.00'),
            },
        )

    def create_profile(self, email, plan=None, referred_by=None, completed=True):
        user = User.objects.create_user(
            username=email,
            email=email,
            password='FreshPass123!',
        )
        return UserProfile.objects.create(
            user=user,
            full_name=email.split('@')[0],
            email_address=email,
            subscription_plan=plan or self.bronze,
            subscription_status=self.completed_status if completed else None,
            referred_by=referred_by,
            is_active=True,
        )

    def test_membership_approval_credits_direct_referral_reward_once(self):
        referrer = self.create_profile('referrer@example.com', plan=self.bronze)
        referred = self.create_profile('referred@example.com', plan=self.silver, referred_by=referrer)

        result = process_approved_membership(referred)

        self.assertTrue(result['processed'])
        points = RewardPoints.objects.get(user_profile=referrer)
        self.assertEqual(points.referral_rewards, Decimal('50.00'))
        self.assertEqual(
            RewardLedger.objects.filter(
                user_profile=referrer,
                reward_type=RewardLedger.RewardType.DIRECT_REFERRAL,
            ).count(),
            1,
        )

        process_approved_membership(referred)
        points.refresh_from_db()
        self.assertEqual(points.referral_rewards, Decimal('50.00'))

    def test_global_pool_caps_receiver_and_redistributes_remaining_share(self):
        capped_receiver = self.create_profile('capped@example.com', plan=self.bronze)
        open_receiver = self.create_profile('open@example.com', plan=self.silver)
        trigger = self.create_profile('trigger@example.com', plan=self.bronze)
        child_one = self.create_profile('child1@example.com', plan=self.bronze)
        child_two = self.create_profile('child2@example.com', plan=self.bronze)

        GlobalPoolMember.objects.create(
            user_profile=capped_receiver,
            qualified_at=capped_receiver.created_at,
            current_plan=self.bronze,
            max_pool_limit=Decimal('2999.00'),
            total_pool_earned=Decimal('2899.00'),
            status=GlobalPoolMember.StatusChoices.ACTIVE,
        )
        GlobalPoolMember.objects.create(
            user_profile=open_receiver,
            qualified_at=open_receiver.created_at,
            current_plan=self.silver,
            max_pool_limit=Decimal('11999.00'),
            total_pool_earned=Decimal('0.00'),
            status=GlobalPoolMember.StatusChoices.ACTIVE,
        )
        ReferralEdge.objects.create(parent=trigger, child=child_one, status=ReferralEdge.StatusChoices.COMPLETED)
        ReferralEdge.objects.create(parent=trigger, child=child_two, status=ReferralEdge.StatusChoices.COMPLETED)

        evaluate_global_pool_for_profile(
            trigger,
            paid_amount=Decimal('5000.00'),
            membership_reference='test:trigger',
        )

        capped_member = GlobalPoolMember.objects.get(user_profile=capped_receiver)
        open_member = GlobalPoolMember.objects.get(user_profile=open_receiver)
        trigger_member = GlobalPoolMember.objects.get(user_profile=trigger)

        self.assertEqual(capped_member.total_pool_earned, Decimal('2999.00'))
        self.assertEqual(capped_member.status, GlobalPoolMember.StatusChoices.EXITED)
        self.assertEqual(open_member.total_pool_earned, Decimal('500.00'))
        self.assertEqual(trigger_member.status, GlobalPoolMember.StatusChoices.ACTIVE)
