from django.contrib import admin
from django.urls import path

from dashboard.views import command_centre

urlpatterns = [
    path('', command_centre, name='command_centre'),
    path('admin/', admin.site.urls),
]
