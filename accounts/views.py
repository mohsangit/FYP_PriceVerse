from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.views import PasswordResetView
from django.shortcuts import render, redirect
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from urllib.parse import urlencode

from .forms import LoginForm, PasswordResetRequestForm, SignupForm

try:
    from smtplib import SMTPAuthenticationError
except ImportError:
    SMTPAuthenticationError = type(None)


class CustomPasswordResetView(PasswordResetView):
    form_class = PasswordResetRequestForm
    template_name = "accounts/password_reset_form.html"
    email_template_name = "accounts/emails/password_reset.txt"
    html_email_template_name = "accounts/emails/password_reset.html"
    subject_template_name = "accounts/emails/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")

    def get_extra_email_context(self):
        return {"site_url": settings.SITE_URL.rstrip("/")}

    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except SMTPAuthenticationError:
            messages.error(
                self.request,
                "Gmail rejected the credentials for "
                f"{settings.EMAIL_HOST_USER}. Sign in to that Gmail account, create an "
                "App Password at Google Account → Security → App passwords, "
                "paste it into EMAIL_HOST_PASSWORD in .env, then restart the server.",
            )
            return self.form_invalid(form)
        except Exception:
            messages.error(
                self.request,
                "We could not send the reset email. Please try again in a few minutes.",
            )
            return self.form_invalid(form)


def _safe_next_url(request, fallback="core:home"):
    next_url = (request.GET.get("next") or request.POST.get("next") or "").strip()
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return reverse(fallback)


def login_view(request):
    if request.user.is_authenticated:
        return redirect("core:home")

    form = LoginForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].strip().lower()
        password = form.cleaned_data["password"]
        remember = form.cleaned_data.get("remember", False)

        # 1) If user with email not found → redirect to signup
        if not User.objects.filter(email__iexact=email).exists():
            messages.info(request, "Account not found. Please sign up first.")
            return redirect(f"{reverse('accounts:signup')}?{urlencode({'email': email})}")

        # 2) Authenticate by username (Django default) but we take email input
        user_obj = User.objects.filter(email__iexact=email).first()
        user = authenticate(request, username=user_obj.username, password=password)

        if user is None:
            messages.error(request, "Invalid password. Please try again.")
            return render(request, "accounts/login.html", {"form": form})

        login(request, user)

        # Remember me logic
        if remember:
            request.session.set_expiry(60 * 60 * 24 * 14)  # 14 days
        else:
            request.session.set_expiry(0)  # browser close

        messages.success(request, "Logged in successfully.")
        return redirect(_safe_next_url(request))

    return render(request, "accounts/login.html", {"form": form, "next": request.GET.get("next", "")})


def signup_view(request):
    if request.user.is_authenticated:
        return redirect("core:home")

    initial_email = request.GET.get("email", "").strip().lower()
    form = SignupForm(request.POST or None, initial={"email": initial_email})

    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Account created successfully.")
        return redirect("core:home")

    return render(request, "accounts/signup.html", {"form": form})


def logout_view(request):
    logout(request)
    messages.info(request, "Logged out.")
    return redirect("core:home")
