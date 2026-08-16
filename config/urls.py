from django.urls import include, path

urlpatterns = [
    path("", include("apps.dashboard.urls")),
]
