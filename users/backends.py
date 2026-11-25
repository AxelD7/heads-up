from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class UsernameOrEmailBackend(ModelBackend):
    """
    Lets people log in with either their username or their email address.

    Django calls authenticate() on each backend listed in AUTHENTICATION_BACKENDS
    in settings.py. ModelBackend (Django's default) only looks up by username,
    so we look the user up by email if the text contains an "@".
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username and "@" in username:
            UserModel = get_user_model()
            user = UserModel.objects.filter(email__iexact=username).first()
            if user is not None:
                username = user.get_username()
        return super().authenticate(request, username=username, password=password, **kwargs)
