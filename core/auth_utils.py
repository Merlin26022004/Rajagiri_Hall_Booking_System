from django.contrib.auth.hashers import make_password, check_password
from core.models import CustomUser

def hash_user_password(raw_password):
    """
    Hashes a password using Django's standard make_password.
    """
    return make_password(raw_password)


def verify_password(raw_password, hashed_password):
    """
    Verifies a password using Django's check_password.
    """
    return check_password(raw_password, hashed_password)


def authenticate_user(email, password):
    """
    Authenticates a user by email and password.
    Returns the CustomUser object if successful, None otherwise.
    """
    try:
        user = CustomUser.objects.get(email=email)
        if verify_password(password, user.password):
            if user.is_active:
                return user
    except CustomUser.DoesNotExist:
        pass
    return None


def login_user(request, user):
    """
    Logs in a user by setting session variables.
    """
    request.session['user_id'] = user.id
    request.session['role'] = user.role
    request.session['full_name'] = user.full_name


def logout_user(request):
    """
    Logs out a user by clearing the session.
    """
    request.session.flush()


def get_current_user(request):
    """
    Retrieves the current logged-in CustomUser based on session.
    Returns None if not logged in.
    """
    user_id = request.session.get('user_id')
    if user_id:
        try:
            return CustomUser.objects.get(id=user_id)
        except CustomUser.DoesNotExist:
            pass
    return None
