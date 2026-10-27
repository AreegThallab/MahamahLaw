import re
from django import forms
from django.utils.html import strip_tags

class SubmissionForm(forms.Form):
    company_website = forms.CharField(required=False)
    name = forms.CharField(min_length=2, max_length=120)
    def __init__(self, data=None, *args, **kwargs):
        if data is not None:
            data = data.copy()
            for field in self.base_fields:
                if field != 'company_website' and field in data:
                    data[field] = strip_tags(data[field]).strip()
            if data.get('email'):
                data['email'] = data['email'].lower()
        super().__init__(data, *args, **kwargs)
    def clean_company_website(self):
        if self.cleaned_data.get('company_website'):
            raise forms.ValidationError('تعذر إرسال النموذج.')
        return ''

class ReviewForm(SubmissionForm):
    rating = forms.IntegerField(min_value=1, max_value=5, widget=forms.Select(
        choices=[('', 'اختر التقييم')] + [(value, f'{value} من 5') for value in range(1,6)]))
    review = forms.CharField(min_length=10, max_length=1200)

class ContactForm(SubmissionForm):
    phone = forms.RegexField(regex=re.compile(r'^[0-9+()\s-]{8,25}$'), error_messages={'invalid': 'صيغة رقم الجوال غير صحيحة.'})
    email = forms.EmailField(required=False, max_length=150)
    service = forms.CharField(max_length=120)
    message = forms.CharField(min_length=10, max_length=2000)
