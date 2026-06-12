from django import forms
from django.contrib.auth.forms import AuthenticationForm

from .models import AdminAccount, GlobalPoolSetting, NotificationRule, SubscriptionMasterPlan, UserProfile


class DashboardLoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(
            attrs={
                'class': 'w-full rounded-lg border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-teal-600 focus:ring-2 focus:ring-teal-100',
                'placeholder': 'Username',
                'autocomplete': 'username',
            }
        )
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                'class': 'w-full rounded-lg border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-teal-600 focus:ring-2 focus:ring-teal-100',
                'placeholder': 'Password',
                'autocomplete': 'current-password',
            }
        )
    )


class AdminDashboardLoginForm(forms.Form):
    username = forms.CharField(
        widget=forms.TextInput(
            attrs={
                'class': 'w-full rounded-lg border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-violet-600 focus:ring-2 focus:ring-violet-100',
                'placeholder': 'Username',
                'autocomplete': 'username',
            }
        )
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                'class': 'w-full rounded-lg border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-violet-600 focus:ring-2 focus:ring-violet-100',
                'placeholder': 'Password',
                'autocomplete': 'current-password',
            }
        )
    )

    def clean(self):
        cleaned_data = super().clean()
        username = cleaned_data.get('username')
        password = cleaned_data.get('password')

        if not username or not password:
            return cleaned_data

        try:
            admin_account = AdminAccount.objects.get(username=username, is_active=True)
        except AdminAccount.DoesNotExist:
            raise forms.ValidationError('Invalid admin credentials.')

        if not admin_account.check_password(password):
            raise forms.ValidationError('Invalid admin credentials.')

        cleaned_data['admin_account'] = admin_account
        return cleaned_data


class SubscriptionPlanForm(forms.ModelForm):
    class Meta:
        model = SubscriptionMasterPlan
        fields = (
            'plan_name',
            'plan_price',
            'monthly_reward',
            'yearly_reward',
            'global_pool_limit',
            'refundable',
            'non_refundable',
        )
        widgets = {
            'plan_name': forms.TextInput(
                attrs={
                    'class': 'w-full rounded-lg border border-slate-200 px-4 py-3 text-sm outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100',
                    'placeholder': 'Example: Gold Flexible Plan',
                }
            ),
            'plan_price': forms.NumberInput(
                attrs={
                    'class': 'w-full rounded-lg border border-slate-200 px-4 py-3 text-sm outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100',
                    'placeholder': '9999.00',
                    'step': '0.01',
                    'min': '0',
                }
            ),
            'monthly_reward': forms.NumberInput(
                attrs={
                    'class': 'w-full rounded-lg border border-slate-200 px-4 py-3 text-sm outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100',
                    'placeholder': '500.00',
                    'step': '0.01',
                    'min': '0',
                }
            ),
            'yearly_reward': forms.NumberInput(
                attrs={
                    'class': 'w-full rounded-lg border border-slate-200 px-4 py-3 text-sm outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100',
                    'placeholder': '6000.00',
                    'step': '0.01',
                    'min': '0',
                }
            ),
            'global_pool_limit': forms.NumberInput(
                attrs={
                    'class': 'w-full rounded-lg border border-slate-200 px-4 py-3 text-sm outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100',
                    'placeholder': '2999.00',
                    'step': '0.01',
                    'min': '0',
                }
            ),
            'refundable': forms.CheckboxInput(
                attrs={
                    'class': 'h-4 w-4 rounded border-slate-300 text-violet-600 focus:ring-violet-500',
                }
            ),
            'non_refundable': forms.CheckboxInput(
                attrs={
                    'class': 'h-4 w-4 rounded border-slate-300 text-violet-600 focus:ring-violet-500',
                }
            ),
        }


class GlobalPoolSettingForm(forms.ModelForm):
    class Meta:
        model = GlobalPoolSetting
        fields = (
            'membership_contribution_percentage',
            'business_net_profit_amount',
            'is_active',
        )
        widgets = {
            'membership_contribution_percentage': forms.NumberInput(
                attrs={
                    'class': 'w-full rounded-lg border border-slate-200 px-4 py-3 text-sm outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100',
                    'step': '0.001',
                    'min': '0',
                    'placeholder': '10.000',
                }
            ),
            'business_net_profit_amount': forms.NumberInput(
                attrs={
                    'class': 'w-full rounded-lg border border-slate-200 px-4 py-3 text-sm outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100',
                    'step': '0.01',
                    'min': '0',
                    'placeholder': '1000.00',
                }
            ),
            'is_active': forms.CheckboxInput(
                attrs={
                    'class': 'h-4 w-4 rounded border-slate-300 text-violet-600 focus:ring-violet-500',
                }
            ),
        }


class UserDashboardProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = (
            'full_name',
            'dob',
            'pan_no',
            'gender',
            'nationality',
            'address',
            'city',
            'state',
            'postal_code',
            'phone_number',
            'email_address',
            'how_did_you_hear_about_club',
        )
        widgets = {
            'dob': forms.DateInput(
                attrs={
                    'type': 'date',
                    'class': 'w-full rounded-lg border border-slate-200 px-4 py-3 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-100',
                },
                format='%Y-%m-%d',
            ),
            'address': forms.Textarea(
                attrs={
                    'rows': 3,
                    'class': 'w-full rounded-lg border border-slate-200 px-4 py-3 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-100',
                }
            ),
            'how_did_you_hear_about_club': forms.TextInput(
                attrs={
                    'class': 'w-full rounded-lg border border-slate-200 px-4 py-3 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-100',
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        input_class = 'w-full rounded-lg border border-slate-200 px-4 py-3 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-100'
        for field_name, field in self.fields.items():
            if field_name == 'dob':
                continue
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs.setdefault('class', input_class)
            else:
                field.widget.attrs.update({'class': input_class})


class AdminProfileCompletionForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = (
            'full_name',
            'dob',
            'pan_no',
            'gender',
            'nationality',
            'address',
            'city',
            'state',
            'postal_code',
            'phone_number',
            'email_address',
            'nominee_full_name',
            'nominee_relationship',
            'nominee_phone_number',
            'how_did_you_hear_about_club',
            'payment_details',
            'uploaded_form_document',
            'subscription_plan',
            'subscription_status',
            'is_active',
        )
        widgets = {
            'dob': forms.DateInput(attrs={'type': 'date'}),
            'address': forms.Textarea(attrs={'rows': 3}),
            'payment_details': forms.Textarea(attrs={'rows': 4}),
            'how_did_you_hear_about_club': forms.TextInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        input_class = 'w-full rounded-lg border border-slate-200 px-4 py-3 text-sm outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100'
        checkbox_class = 'h-4 w-4 rounded border-slate-300 text-violet-600 focus:ring-violet-500'

        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({'class': checkbox_class})
            elif isinstance(field.widget, forms.FileInput):
                field.widget.attrs.update({'class': 'w-full rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm'})
            else:
                field.widget.attrs.update({'class': input_class})


class NotificationRuleForm(forms.ModelForm):
    class Meta:
        model = NotificationRule
        fields = (
            'title_template',
            'message_template',
            'deep_link',
            'send_immediately',
            'is_active',
        )
        widgets = {
            'title_template': forms.TextInput(
                attrs={
                    'class': 'w-full rounded-lg border border-slate-200 px-4 py-3 text-sm outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100',
                    'placeholder': 'Example: Subscription Approved',
                }
            ),
            'message_template': forms.Textarea(
                attrs={
                    'class': 'w-full rounded-lg border border-slate-200 px-4 py-3 text-sm outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100',
                    'rows': 8,
                    'placeholder': 'Example: Hello {full_name}, your {plan_name} subscription has been approved.',
                }
            ),
            'deep_link': forms.TextInput(
                attrs={
                    'class': 'w-full rounded-lg border border-slate-200 px-4 py-3 text-sm outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100',
                    'placeholder': 'Example: app://subscription/status',
                }
            ),
            'send_immediately': forms.CheckboxInput(
                attrs={
                    'class': 'h-4 w-4 rounded border-slate-300 text-violet-600 focus:ring-violet-500',
                }
            ),
            'is_active': forms.CheckboxInput(
                attrs={
                    'class': 'h-4 w-4 rounded border-slate-300 text-violet-600 focus:ring-violet-500',
                }
            ),
        }
