from django.shortcuts import render

def home(request):
    return render(request, 'static_pages/home.html')

def membership(request):
    return render(request, 'static_pages/membership.html')

def plan_checkout(request):
    return render(request, 'static_pages/plan_checkout.html')