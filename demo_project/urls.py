
from django.urls import path, include

urlpatterns = [
    path('api/routing/', include('routing.urls')),
]
