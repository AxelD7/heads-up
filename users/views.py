from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render

from .forms import LoginForm, SignUpForm


def index(request):
    context = {
        'message': "Hello world from users app!"
    }

    return render(request, 'index.html', context)


class UserLoginView(LoginView):
    """
    Log in page at /login/.

    Django's LoginView does the real work: it checks the username/password,
    starts the session, and sends the user to ?next=... or LOGIN_REDIRECT_URL.
    """

    template_name = "users/login.html"
    authentication_form = LoginForm
    # If someone who is already logged in visits /login/, just send them to the dashboard.
    redirect_authenticated_user = True


def signup(request):
    """
    Sign up page at /signup/.

    GET shows an empty form. POST checks the form, creates the user,
    logs them in straight away and sends them to the dashboard.
    """
    if request.user.is_authenticated:
        return redirect("events:event_list")

    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("events:event_list")
    else:
        form = SignUpForm()

    return render(request, "users/signup.html", {"form": form})
