from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("chat/", views.chat_view, name="chat"),
    path("history/", views.history_view, name="history"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("register/", views.register_view, name="register"),
    path("change-credentials/", views.change_credentials_view, name="change_credentials"),
    path("dashboard/users/<int:user_id>/", views.dashboard_user_view, name="dashboard_user_view"),
    path("dashboard/users/<int:user_id>/edit/", views.dashboard_user_edit, name="dashboard_user_edit"),
    path("dashboard/users/<int:user_id>/delete/", views.dashboard_user_delete, name="dashboard_user_delete"),
]
