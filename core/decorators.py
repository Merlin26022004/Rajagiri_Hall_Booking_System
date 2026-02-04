from functools import wraps
from django.shortcuts import render

def approval_required(view_func):
    """
    Decorator that checks if the user belongs to an approved group 
    or is a Superuser.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        
        # 1. ALWAYS Allow Superusers (Admins)
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        
        # 2. Check if user belongs to approved groups
        allowed_groups = ['Faculty', 'Student Rep', 'Transport Officer']
        if request.user.groups.filter(name__in=allowed_groups).exists():
            return view_func(request, *args, **kwargs)

        # 3. If rejected, show the waiting room
        # Django automatically looks inside "core/templates/", so we just say:
        return render(request, 'core/waiting_room.html') 

    return _wrapped_view