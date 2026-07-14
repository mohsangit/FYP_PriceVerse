from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Send a test email using the configured SMTP settings."

    def handle(self, *args, **options):
        if not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
            self.stderr.write(
                self.style.ERROR(
                    "EMAIL_HOST_USER and EMAIL_HOST_PASSWORD must be set in .env"
                )
            )
            return

        self.stdout.write(f"Backend: {settings.EMAIL_BACKEND}")
        self.stdout.write(f"User: {settings.EMAIL_HOST_USER}")
        self.stdout.write(f"Password length: {len(settings.EMAIL_HOST_PASSWORD)} chars")

        if len(settings.EMAIL_HOST_PASSWORD) != 16:
            self.stdout.write(
                self.style.WARNING(
                    "Gmail App Passwords are exactly 16 characters. "
                    "Your password length suggests a regular login password."
                )
            )

        try:
            send_mail(
                subject="PriceVerse email test",
                message="If you received this, SMTP is working.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[settings.EMAIL_HOST_USER],
                fail_silently=False,
            )
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"FAILED: {exc}"))
            return

        self.stdout.write(self.style.SUCCESS("Test email sent successfully."))
