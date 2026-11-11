from django.shortcuts import render
from django.contrib.auth.decorators import login_required

# Event views
@login_required()
def dashboard(request):
    
    context = {
        "message": "Hello from the dashboard"
    }
    
    return render(request, "dashboard.html", context)

