from django.contrib import messages
from django.contrib.admin.models import LogEntry, CHANGE
from django.contrib.auth import get_user_model
from django.contrib.auth.views import LoginView
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from apps.core.models import ContactRequest, Review
from apps.core.views import throttle
from .access import staff_permissions
from .forms import StaffAuthenticationForm, RequestUpdateForm, RejectReviewForm, PreferencesForm, DateRangeForm

VIEW_REQUESTS = 'core.view_contactrequest'
VIEW_REVIEWS = 'core.view_review'
STATUS_COLORS = {'new':'#c69957', 'in_progress':'#e6cba5', 'contacted':'#52a480', 'closed':'#9a9da1'}

class DashboardLogin(LoginView):
    template_name = 'dashboard/login.html'
    authentication_form = StaffAuthenticationForm
    def post(self, request, *args, **kwargs):
        limited = throttle(request, 'dashboard-login', 5)
        return limited if limited is not None else super().post(request, *args, **kwargs)
    def get_success_url(self):
        target = self.get_redirect_url()
        if target:
            return target
        user = self.request.user
        if user.has_perms([VIEW_REQUESTS, VIEW_REVIEWS]):
            return reverse('dashboard:home')
        for permission, route in [(VIEW_REQUESTS,'consultations'),(VIEW_REVIEWS,'reviews'),('accounts.view_user','users')]:
            if user.has_perm(permission):
                return reverse('dashboard:'+route)
        return reverse('dashboard:settings')

def preference_values(request):
    prefs = request.session.get('dashboard_preferences', {})
    page_size = prefs.get('page_size', 10)
    if page_size not in (10,20,50):
        page_size = 10
    return {'page_size':page_size, 'live_updates':bool(prefs.get('live_updates', True))}

def common(request):
    return {**preference_values(request), 'stars':range(1,6),
            'new_count': ContactRequest.objects.filter(status='new',request_type='consultation').count() if request.user.has_perm(VIEW_REQUESTS) else 0}

def render_dashboard(request, template, context):
    return render(request, template, {**common(request), **context})

def request_queryset(request, kind, prefix=''):
    query = request.GET.get(prefix+'q', '').strip()[:200]
    status = request.GET.get(prefix+'status', '')
    rows = ContactRequest.objects.filter(request_type=kind)
    if query:
        rows = rows.filter(Q(name__icontains=query) | Q(phone__icontains=query) | Q(email__icontains=query) | Q(service__icontains=query) | Q(message__icontains=query))
    if status:
        rows = rows.filter(status=status) if status in ContactRequest.Status.values else rows.none()
    return rows, query, status

def review_queryset(request, prefix=''):
    query = request.GET.get(prefix+'q', '').strip()[:200]
    rows = Review.objects.all()
    if query:
        rows = rows.filter(Q(name__icontains=query) | Q(review__icontains=query))
    return rows, query

def status_chart(rows):
    counts = dict(rows.order_by().values_list('status').annotate(total=Count('pk')))
    total = sum(counts.values())
    position, stops, legend = 0, [], []
    for key, label in ContactRequest.Status.choices:
        count = counts.get(key, 0)
        end = position + (count * 100 / total if total else 0)
        color = STATUS_COLORS[key]
        if count:
            stops.append(f'{color} {position:.3f}% {end:.3f}%')
        legend.append({'key':key, 'label':label, 'count':count, 'color':color})
        position = end
    return {'total':total, 'legend':legend, 'gradient':'conic-gradient('+','.join(stops)+')' if stops else '#e8e9eb'}

def home_data(request):
    rows, query, status = request_queryset(request, 'consultation', 'r')
    reviews, review_query = review_queryset(request, 'v')
    return {'request_rows':Paginator(rows, 5).get_page(request.GET.get('rpage')),
            'review_rows':Paginator(reviews, 5).get_page(request.GET.get('vpage')),
            'request_query':query, 'selected_status':status, 'review_query':review_query,
            'request_prefix':'r', 'review_prefix':'v', 'request_page_param':'rpage', 'review_page_param':'vpage',
            'chart':status_chart(ContactRequest.objects.filter(request_type='consultation')),
            'status_choices':ContactRequest.Status.choices, 'home_view':True}

@staff_permissions(VIEW_REQUESTS, VIEW_REVIEWS)
@require_GET
def home(request):
    return render_dashboard(request, 'dashboard/home.html', {'section':'home','page_title':'الرئيسية', **home_data(request)})

def list_data(request, kind):
    rows, query, status = request_queryset(request, kind)
    return {'request_rows':Paginator(rows, preference_values(request)['page_size']).get_page(request.GET.get('page')),
            'request_query':query, 'selected_status':status, 'request_prefix':'', 'request_page_param':'page',
            'status_choices':ContactRequest.Status.choices, 'request_kind':kind,
            'chart':status_chart(ContactRequest.objects.filter(request_type=kind))}

@staff_permissions(VIEW_REQUESTS)
@require_GET
def requests_list(request, kind):
    title = 'طلبات الاستشارات' if kind == 'consultation' else 'طلبات التواصل'
    return render_dashboard(request, 'dashboard/requests.html', {'section':'consultations' if kind=='consultation' else 'contacts', 'page_title':title, **list_data(request,kind)})

def reviews_data(request):
    rows, query = review_queryset(request)
    return {'review_rows':Paginator(rows,preference_values(request)['page_size']).get_page(request.GET.get('page')),
            'review_query':query, 'review_prefix':'', 'review_page_param':'page'}

@staff_permissions(VIEW_REVIEWS)
@require_GET
def reviews_list(request):
    return render_dashboard(request, 'dashboard/reviews.html', {'section':'reviews','page_title':'تقييمات العملاء', **reviews_data(request)})

@staff_permissions()
@require_GET
def live(request):
    mode = request.GET.get('mode', 'home')
    if mode == 'home':
        permissions, template = [VIEW_REQUESTS,VIEW_REVIEWS], 'dashboard/includes/home_data.html'
    elif mode in ('consultation','contact'):
        permissions, template = [VIEW_REQUESTS], 'dashboard/includes/request_panel.html'
    elif mode == 'reviews':
        permissions, template = [VIEW_REVIEWS], 'dashboard/includes/review_panel.html'
    else:
        return JsonResponse({'error':'Unknown section'},status=400)
    if not request.user.has_perms(permissions):
        raise PermissionDenied
    if mode == 'home':
        context = home_data(request)
    elif mode == 'reviews':
        context = reviews_data(request)
    else:
        context = list_data(request,mode)
    html = render_to_string(template, {**common(request), **context}, request=request)
    return JsonResponse({'html':html, 'updated_at':timezone.now().isoformat()})

def audit(user, instance, description):
    LogEntry.objects.create(user_id=user.pk, content_type=ContentType.objects.get_for_model(instance),
                            object_id=str(instance.pk), object_repr=f'{instance._meta.verbose_name} #{instance.pk}',
                            action_flag=CHANGE, change_message=description)

@staff_permissions(VIEW_REQUESTS)
@require_http_methods(['GET','POST'])
def request_detail(request, pk):
    item = get_object_or_404(ContactRequest,pk=pk)
    can_change = request.user.has_perm('core.change_contactrequest')
    if request.method == 'POST' and not can_change:
        raise PermissionDenied
    form = RequestUpdateForm(request.POST if request.method=='POST' else None, instance=item)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            changed = form.save(commit=False)
            changed.updated_at = timezone.now()
            changed.save(update_fields=['status','request_type','internal_notes','updated_at'])
            audit(request.user, changed, 'Updated request status/type/internal notes through dashboard.')
        messages.success(request,'تم تحديث الطلب بنجاح.')
        return redirect('dashboard:request-detail',pk=pk)
    return render_dashboard(request,'dashboard/request_detail.html', {'section':'contacts' if item.request_type=='contact' else 'consultations',
                            'page_title':f'تفاصيل الطلب #{item.pk}', 'item':item,'form':form,'can_change':can_change})

@staff_permissions(VIEW_REVIEWS)
@require_GET
def review_detail(request, pk):
    item = get_object_or_404(Review,pk=pk)
    return render_dashboard(request,'dashboard/review_detail.html',{'section':'reviews','page_title':'تفاصيل التقييم', 'item':item})

@staff_permissions(VIEW_REVIEWS, 'core.change_review')
@require_POST
def review_approve(request,pk):
    with transaction.atomic():
        item = get_object_or_404(Review,pk=pk)
        if item.status != 'approved':
            item.status, item.updated_at = 'approved', timezone.now()
            item.save(update_fields=['status','updated_at'])
            audit(request.user,item,'Approved review for publication.')
    messages.success(request,'تم اعتماد التقييم ونشره بنجاح.' if not item.is_demo else 'تم اعتماد النموذج التجريبي؛ سيظهر بعلامة تجريبية في بيئة التطوير فقط.')
    return redirect('dashboard:review-detail',pk=pk)

@staff_permissions(VIEW_REVIEWS, 'core.change_review')
@require_http_methods(['GET','POST'])
def review_reject(request,pk):
    item = get_object_or_404(Review,pk=pk)
    form = RejectReviewForm(request.POST if request.method=='POST' else None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            if item.status != 'rejected':
                item.status, item.updated_at = 'rejected', timezone.now()
                item.save(update_fields=['status','updated_at'])
                audit(request.user,item,'Rejected review; public visibility removed.')
        messages.success(request,'تم رفض التقييم ولن يظهر في الموقع.')
        return redirect('dashboard:reviews')
    return render_dashboard(request,'dashboard/reject.html',{'section':'reviews','page_title':'تأكيد رفض التقييم','item':item,'form':form})

@staff_permissions('accounts.view_user')
@require_GET
def users(request):
    query = request.GET.get('q','').strip()[:200]
    rows = get_user_model().objects.filter(is_staff=True).order_by('username')
    if query:
        rows = rows.filter(Q(username__icontains=query)|Q(name__icontains=query)|Q(email__icontains=query))
    return render_dashboard(request,'dashboard/users.html', {'section':'users','page_title':'المستخدمون', 'query':query,
                            'user_rows':Paginator(rows,preference_values(request)['page_size']).get_page(request.GET.get('page'))})

@staff_permissions(VIEW_REQUESTS, VIEW_REVIEWS)
@require_GET
def reports(request):
    form = DateRangeForm(request.GET or None)
    requests, reviews = ContactRequest.objects.all(), Review.objects.all()
    if form.is_bound:
        if form.is_valid():
            for field,lookup in [('start','gte'),('end','lte')]:
                if form.cleaned_data[field]:
                    requests = requests.filter(**{'created_at__date__'+lookup:form.cleaned_data[field]})
                    reviews = reviews.filter(**{'created_at__date__'+lookup:form.cleaned_data[field]})
        else:
            requests, reviews = requests.none(), reviews.none()
    # Null dates from historical imports remain in totals, but not dated trends.
    trends = requests.filter(created_at__isnull=False).annotate(day=TruncDate('created_at')).values('day').annotate(total=Count('pk')).order_by('-day')
    review_counts = dict(reviews.order_by().values_list('status').annotate(total=Count('pk')))
    trend_page = Paginator(trends,31).get_page(request.GET.get('page'))
    return render_dashboard(request,'dashboard/reports.html',{'section':'reports','page_title':'التقارير','form':form,
        'chart':status_chart(requests.filter(request_type='consultation')),
        'contact_chart':status_chart(requests.filter(request_type='contact')), 'trend_rows':trend_page,
        'review_totals':[(label,review_counts.get(key,0)) for key,label in [('pending','بانتظار المراجعة'),('approved','معتمدة'),('rejected','مرفوضة')]],
        'demo_count':requests.filter(is_demo=True).count()+reviews.filter(is_demo=True).count()})

@staff_permissions()
@require_http_methods(['GET','POST'])
def preferences(request):
    form = PreferencesForm(request.POST if request.method=='POST' else None, initial=preference_values(request))
    if request.method=='POST' and form.is_valid():
        request.session['dashboard_preferences'] = form.cleaned_data
        messages.success(request,'تم حفظ تفضيلات لوحة الإدارة لهذه الجلسة.')
        return redirect('dashboard:settings')
    return render_dashboard(request,'dashboard/settings.html',{'section':'settings','page_title':'الإعدادات','form':form})
