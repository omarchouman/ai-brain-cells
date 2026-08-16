from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("setup/", views.setup, name="setup"),
    path("setup/create/", views.create_brain, name="create_brain"),
    path("notes/", views.notes, name="notes"),
    path("notes/new/", views.note_new, name="note_new"),
    path("notes/<str:note_id>/", views.note_edit, name="note_edit"),
    path("notes/<str:note_id>/delete/", views.note_delete, name="note_delete"),
    path("preview/", views.preview, name="preview"),
]
