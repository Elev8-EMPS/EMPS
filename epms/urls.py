from django.contrib import admin
from django.urls import include, path

from dashboard.views import command_centre

urlpatterns = [
    path('', command_centre, name='command_centre'),
    path('', include('crm.urls')),
    path('', include('delivery.urls')),
    path('', include('finance.urls')),
    path('', include('leave.urls')),
    path('', include('security.urls')),
    path('', include('tenants.urls')),
    path('admin/', admin.site.urls),
]
