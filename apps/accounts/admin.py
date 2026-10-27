from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User

@admin.register(User)
class AccountAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (('Laravel profile', {'fields': ('name', 'email_verified_at', 'created_at', 'updated_at')}),)
