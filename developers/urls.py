from django.urls import path
from . import api_views

urlpatterns = [
    path('health/', api_views.developers_health, name='developers-health'),
    path('dashboard/', api_views.developers_dashboard, name='developers-dashboard'),
    path('<int:dev_id>/', api_views.developer_detail, name='developer-detail'),
]
