from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("setup/", views.setup, name="setup"),
    path("setup/create/", views.create_brain, name="create_brain"),
]
