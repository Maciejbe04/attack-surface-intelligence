from django.urls import path

from .system import SystemInfoView
from .views import health

urlpatterns = [
    path("health/", health, name="health"),
    path("system/", SystemInfoView.as_view(), name="system-info"),
]
