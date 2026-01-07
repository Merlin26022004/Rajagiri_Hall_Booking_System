from functools import wraps
from django.shortcuts import redirect, render
from django.contrib import messages

def custom_login_required(view_func):
    """
    Decorator to ensure the user is logged in (session has user_id).
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if 'user_id' not in request.session:
            messages.error(request, "You must be logged in to view this page.")
            return redirect('login') 
        return view_func(request, *args, **kwargs)
    return wrapper


def role_required(allowed_roles):
    """
    Decorator to restrict access to specific roles.
    allowed_roles: list of role strings (e.g. ['SUPER_ADMIN', 'RECEPTIONIST'])
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if 'user_id' not in request.session:
                return redirect('login')
            
            user_role = request.session.get('role')
            if user_role not in allowed_roles:
                return render(request, '403.html', status=403)
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
