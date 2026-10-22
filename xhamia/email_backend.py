from django.core.mail.backends.smtp import EmailBackend


class GmailBackend(EmailBackend):
    """SMTP i Gmail-it që e merr fjalëkalimin nga faqja "SMS & Email" nëse është
    vendosur atje; përndryshe nga EMAIL_HOST_PASSWORD te settings/local_settings."""

    def __init__(self, *args, password=None, **kwargs):
        if password is None:
            from xhamia.models import KonfigurimiSistemit
            try:
                password = KonfigurimiSistemit.merr().gmail_app_password or None
            except Exception:
                password = None
        super().__init__(*args, password=password, **kwargs)
