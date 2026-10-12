from django.urls import path

from . import views

app_name = "crm"

urlpatterns = [
    path("", views.board, name="board"),
    path("deal/new/", views.deal_new, name="deal_new"),
    path("deal/<int:pk>/", views.deal_detail, name="deal"),
    path("deal/<int:pk>/move/", views.deal_move, name="deal_move"),
    path("tasks/", views.tasks, name="tasks"),
    path("tasks/<int:pk>/done/", views.task_done, name="task_done"),
    path("clients/", views.clients, name="clients"),
    path("clients/<int:pk>/", views.client_detail, name="client"),
    path("reports/", views.report, name="reports"),
    path("lead-file/<int:pk>/", views.lead_file, name="lead_file"),
]
