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
    path("notes/<str:note_id>/supersede/", views.note_supersede, name="note_supersede"),
    path("notes/<str:note_id>/revive/", views.note_revive, name="note_revive"),
    path("notes/<str:note_id>/delete/", views.note_delete, name="note_delete"),
    path("projects/", views.projects, name="projects"),
    path("projects/new/", views.project_new, name="project_new"),
    path("projects/<slug:slug>/", views.project_edit, name="project_edit"),
    path("projects/<slug:slug>/verify/", views.project_verify, name="project_verify"),
    path("projects/<slug:slug>/delete/", views.project_delete, name="project_delete"),
    path("backup/", views.backup, name="backup"),
    path("backup/remote/", views.backup_set_remote, name="backup_set_remote"),
    path("backup/remote/remove/", views.backup_remove_remote, name="backup_remove_remote"),
    path("backup/push/", views.backup_push, name="backup_push"),
    path("skills/", views.skills_page, name="skills"),
    path("skills/install/", views.skills_install, name="skills_install"),
    path("skills/uninstall/", views.skills_uninstall, name="skills_uninstall"),
    path("taxonomy/", views.taxonomy, name="taxonomy"),
    path("lenses/", views.lenses, name="lenses"),
    path("lenses/new/", views.lens_new, name="lens_new"),
    path("lenses/<slug:name>/", views.lens_edit, name="lens_edit"),
    path("lenses/<slug:name>/delete/", views.lens_delete, name="lens_delete"),
    path("identity/", views.identity, name="identity"),
    path("identity/<str:slug>/", views.identity_edit, name="identity_edit"),
    path("preview/", views.preview, name="preview"),
]
