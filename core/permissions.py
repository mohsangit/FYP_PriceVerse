from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect


def is_site_admin(user):
    """Return True if the user is the designated site admin."""
    if not user.is_authenticated:
        return False
    admin_email = (getattr(settings, "ADMIN_EMAIL", "") or "").lower()
    return user.is_superuser or (user.email or "").lower() == admin_email


def admin_required(view_func):
    """Require login and site-admin privileges (Scraper access)."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not is_site_admin(request.user):
            messages.error(request, "You do not have permission to access this page.")
            return redirect("core:home")
        return view_func(request, *args, **kwargs)

    return wrapper
