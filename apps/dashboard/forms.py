from django import forms
from django.contrib.auth.forms import AuthenticationForm
from apps.core.models import ContactRequest

class StaffAuthenticationForm(AuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_staff:
            raise forms.ValidationError('هذا الحساب غير مخوّل بدخول لوحة الإدارة.', code='not_staff')

class RequestUpdateForm(forms.ModelForm):
    class Meta:
        model = ContactRequest
        fields = ['status', 'request_type', 'internal_notes']
        labels = {'status':'حالة الطلب', 'request_type':'نوع الطلب', 'internal_notes':'ملاحظات داخلية'}
        widgets = {'internal_notes':forms.Textarea(attrs={'rows':5, 'maxlength':10000})}
    def clean_internal_notes(self):
        notes = self.cleaned_data['internal_notes']
        if len(notes) > 10000:
            raise forms.ValidationError('الحد الأقصى للملاحظات 10000 حرف.')
        return notes

class RejectReviewForm(forms.Form):
    confirm = forms.BooleanField(label='أؤكد رفض هذا التقييم وإزالته من العرض العام.')

class PreferencesForm(forms.Form):
    page_size = forms.TypedChoiceField(label='عدد السجلات في الصفحة', coerce=int, choices=[(10,'10'),(20,'20'),(50,'50')])
    live_updates = forms.BooleanField(label='تحديث قوائم الطلبات والتقييمات تلقائيًا', required=False)

class DateRangeForm(forms.Form):
    start = forms.DateField(label='من تاريخ', required=False, widget=forms.DateInput(attrs={'type':'date'}))
    end = forms.DateField(label='إلى تاريخ', required=False, widget=forms.DateInput(attrs={'type':'date'}))
    def clean(self):
        data = super().clean()
        if data.get('start') and data.get('end') and data['start'] > data['end']:
            raise forms.ValidationError('تاريخ البداية يجب أن يسبق تاريخ النهاية.')
        return data
