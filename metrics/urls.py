from django.urls import path
from . import api_views

urlpatterns = [
    path('projects/', api_views.project_list, name='project-list'),
    path('projects/<slug:slug>/dashboard/', api_views.project_dashboard, name='project-dashboard'),
    path('projects/<slug:slug>/focus/atc/', api_views.project_focus_atc, name='project-focus-atc'),
    path('projects/<slug:slug>/refresh/', api_views.project_refresh, name='project-refresh'),
    path('webhook/github/', api_views.webhook_github, name='webhook-github'),
]
