from functools import wraps
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.views.decorators.cache import never_cache

def staff_permissions(*permissions):
    def decorate(view):
        @never_cache
        @wraps(view)
        def protected(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                return redirect_to_login(request.get_full_path(), '/dashboard/login/')
            if not user.is_active or not user.is_staff or not user.has_perms(permissions):
                raise PermissionDenied
            response = view(request, *args, **kwargs)
            response['Cache-Control'] = 'private, no-store'
            return response
        return protected
    return decorate
