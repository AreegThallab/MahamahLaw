from django.contrib import admin
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.template.response import TemplateResponse
from django.utils import timezone
from .models import Review, ContactRequest

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    readonly_fields = ('is_demo', 'demo_key')
    list_display = ('name', 'rating', 'status', 'created_at')
    list_filter = ('status', 'rating', 'is_demo')
    search_fields = ('name', 'review')
    actions = ['approve', 'reject']
    @admin.action(description='Approve selected reviews', permissions=['change'])
    def approve(self, request, queryset):
        queryset.update(status='approved', updated_at=timezone.now())
    @admin.action(description='Reject selected reviews', permissions=['change'])
    def reject(self, request, queryset):
        if request.POST.get('confirm_reject') == 'yes':
            queryset.update(status='rejected', updated_at=timezone.now())
            self.message_user(request, 'تم رفض التقييمات المحددة وإزالتها من العرض العام.')
            return None
        return TemplateResponse(request, 'admin/review_reject_confirmation.html', {
            **self.admin_site.each_context(request), 'title':'تأكيد رفض التقييمات',
            'opts':self.model._meta, 'queryset':queryset, 'action_checkbox_name':ACTION_CHECKBOX_NAME,
        })

@admin.register(ContactRequest)
class ContactAdmin(admin.ModelAdmin):
    readonly_fields = ('is_demo', 'demo_key')
    list_display = ('name', 'request_type', 'service', 'status', 'created_at')
    list_filter = ('status', 'request_type', 'service', 'is_demo')
    search_fields = ('name', 'phone', 'email')
