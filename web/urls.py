from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('membership/', views.membership, name='membership'),
    path('membership/checkout/', views.plan_checkout, name='plan_checkout'),
]