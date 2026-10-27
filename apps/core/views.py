import hashlib
import math
import json
from datetime import timedelta
from django.contrib import messages
from django.conf import settings
from django.db import transaction
from django.db.models import F as models_F
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.views.decorators.http import require_GET, require_POST
from .content import CONTENT
from .forms import ContactForm, ReviewForm
from .models import Review, ContactRequest, SubmissionWindow, SubmissionReceipt

def page(request, **extra):
    context = dict(CONTENT)
    reviews = Review.objects.filter(status='approved')
    if not settings.DEBUG:
        reviews = reviews.filter(is_demo=False)
    approved = list(reviews[:8])
    context.update(displayReviews=approved or CONTENT['placeholderReviews'], demo_reviews=not approved,
                   review_form=ReviewForm(), contact_form=ContactForm(), stars=range(1,6))
    context.update(extra)
    return render(request, 'pages/home.html', context)

@require_GET
def home(request):
    return page(request)

def throttle(request, scope, limit):
    # REMOTE_ADDR only: do not trust user-supplied forwarding headers.
    key = hashlib.sha256(f'{scope}:{request.META.get("REMOTE_ADDR", "")}'.encode()).hexdigest()
    now = timezone.now()
    with transaction.atomic():
        # First acquire SQLite's writer lock, before reading the shared window.
        SubmissionWindow.objects.filter(key=key).update(count=models_F('count'))
        window = SubmissionWindow.objects.filter(key=key).first()
        if not window or now >= window.started_at + timedelta(seconds=60):
            SubmissionWindow.objects.update_or_create(key=key, defaults={'started_at': now, 'count': 1})
            return None
        if window.count >= limit:
            response = HttpResponse('طلبات كثيرة، يرجى المحاولة بعد قليل.', status=429)
            response['Retry-After'] = str(max(1, math.ceil((window.started_at + timedelta(seconds=60) - now).total_seconds())))
            return response
        window.count += 1
        window.save(update_fields=['count'])
    return None

def submit(request, form_class, model, scope, limit, fragment, success):
    limited = throttle(request, scope, limit)
    if limited is not None:
        return limited
    form = form_class(request.POST)
    if not form.is_valid():
        return page(request, **{scope + '_form': form, 'error_section': fragment})
    data = dict(form.cleaned_data)
    data.pop('company_website', None)
    if model is ContactRequest:
        data['email'] = data.get('email') or None
    # Serialize the receipt check and insert under the same SQLite writer lock.
    # A rapid retry/double click succeeds without creating a second submission.
    key = salted_hmac('public-submission', json.dumps([scope, request.META.get('REMOTE_ADDR', ''), data], sort_keys=True), algorithm='sha256').hexdigest()
    now = timezone.now()
    with transaction.atomic():
        SubmissionReceipt.objects.filter(key=key).update(expires_at=models_F('expires_at'))
        receipt = SubmissionReceipt.objects.filter(key=key).first()
        if not receipt or receipt.expires_at <= now:
            model.objects.create(**data, created_at=now, updated_at=now)
            SubmissionReceipt.objects.update_or_create(key=key, defaults={'expires_at': now + timedelta(minutes=2)})
    messages.success(request, success, extra_tags=scope)
    return redirect('/#' + fragment)

@require_POST
def review_store(request):
    return submit(request, ReviewForm, Review, 'review', 3, 'testimonials', 'تم استلام رأيك بنجاح، وسيظهر بعد المراجعة والاعتماد.')

@require_POST
def contact_store(request):
    return submit(request, ContactForm, ContactRequest, 'contact', 4, 'contact', 'تم إرسال طلبك بنجاح، وسيتواصل معك الفريق في أقرب وقت مناسب.')
