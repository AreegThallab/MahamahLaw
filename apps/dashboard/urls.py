from django.contrib.auth.views import LogoutView
from django.urls import path
from . import views
from .access import staff_permissions

app_name = 'dashboard'
urlpatterns = [
    path('login/', views.DashboardLogin.as_view(), name='login'),
    path('logout/', staff_permissions()(LogoutView.as_view()), name='logout'),
    path('', views.home, name='home'),
    path('live/', views.live, name='live'),
    path('consultations/', views.requests_list, {'kind':'consultation'}, name='consultations'),
    path('contacts/', views.requests_list, {'kind':'contact'}, name='contacts'),
    path('requests/<int:pk>/', views.request_detail, name='request-detail'),
    path('reviews/', views.reviews_list, name='reviews'),
    path('reviews/<int:pk>/', views.review_detail, name='review-detail'),
    path('reviews/<int:pk>/approve/', views.review_approve, name='review-approve'),
    path('reviews/<int:pk>/reject/', views.review_reject, name='review-reject'),
    path('users/', views.users, name='users'),
    path('reports/', views.reports, name='reports'),
    path('settings/', views.preferences, name='settings'),
]
