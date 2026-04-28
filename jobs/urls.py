from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("register/", views.register, name="register"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("import/", views.import_vacancy, name="import_vacancy"),
    path("applications/new/", views.application_create,
         name="application_create"),
    path("applications/<int:pk>/", views.application_detail,
         name="application_detail"),
    path("applications/<int:pk>/edit/", views.application_edit,
         name="application_edit"),
    path("applications/<int:pk>/delete/", views.application_delete,
         name="application_delete"),
    path('404/', views.custom_page_not_found, {'exception': Exception()}),
]
