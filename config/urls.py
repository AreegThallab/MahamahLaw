from django.contrib import admin
from django.http import HttpResponse
from django.urls import path, include
from apps.core import views

admin.site.site_header = 'إدارة محاماة'
admin.site.site_title = 'محاماة'
urlpatterns = [
    path('', views.home, name='home'),
    path('reviews', views.review_store, name='reviews.store'),
    path('contact-requests', views.contact_store, name='contact.store'),
    path('up', lambda request: HttpResponse('OK'), name='health'),
    path('admin/', admin.site.urls),
    path('dashboard/', include('apps.dashboard.urls')),
]
