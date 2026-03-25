from django.urls import path
from . import views

urlpatterns = [
    path("health/", views.healthcheck_view, name="healthcheck"),
    path("", views.index, name="index"),
    path("reports/", views.report_intake_view, name="report_intake"),
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("analyses/<int:analysis_id>/", views.analysis_detail_view, name="analysis_detail"),
    path(
        "analyses/<int:analysis_id>/treatments/<int:treatment_id>/edit/",
        views.treatment_entry_edit_view,
        name="treatment_entry_edit",
    ),
    path(
        "analyses/<int:analysis_id>/treatments/<int:treatment_id>/delete/",
        views.treatment_entry_delete_view,
        name="treatment_entry_delete",
    ),
    path("chat/", views.chat_view, name="chat"),
    path("history/", views.history_view, name="history"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("register/", views.register_view, name="register"),
    path("register/verify/<uuid:token>/", views.register_verify_view, name="register_verify"),
    path("change-credentials/", views.change_credentials_view, name="change_credentials"),
    path("dashboard/users/<int:user_id>/", views.dashboard_user_view, name="dashboard_user_view"),
    path("dashboard/users/<int:user_id>/edit/", views.dashboard_user_edit, name="dashboard_user_edit"),
    path("dashboard/users/<int:user_id>/delete/", views.dashboard_user_delete, name="dashboard_user_delete"),
]
