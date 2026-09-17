from django.urls import path
from . import views

urlpatterns = [
    # ============================================================
    # Dashboard
    # ============================================================
    path('', views.card_list, name='card_list'),

    # ============================================================
    # Teacher / Staff CRUD
    # ============================================================
    path('cards/new/', views.card_create, name='card_create'),
    path('cards/<int:pk>/', views.card_detail, name='card_detail'),
    path('cards/<int:pk>/edit/', views.card_edit, name='card_edit'),
    path('cards/<int:pk>/delete/', views.card_delete, name='card_delete'),

    # ============================================================
    # Print & PDF
    # ============================================================
    path('cards/<int:pk>/print/', views.card_print, name='card_print'),
    path('cards/<int:pk>/pdf/', views.card_pdf, name='card_pdf'),
    path('print-all/', views.card_print_all, name='card_print_all'),
    path('pdf-all/', views.card_pdf_all, name='card_pdf_all'),

    # ============================================================
    # School Settings
    # ============================================================
    path('settings/', views.school_settings, name='school_settings'),

    # ============================================================
    # Departments
    # ============================================================
    path('departments/', views.department_list, name='department_list'),
    path('departments/new/', views.department_create, name='department_create'),
    path('departments/<int:pk>/edit/', views.department_edit, name='department_edit'),
    path('departments/<int:pk>/delete/', views.department_delete, name='department_delete'),

    # ============================================================
    # Levels
    # ============================================================
    path('levels/', views.level_list, name='level_list'),
    path('levels/new/', views.level_create, name='level_create'),
    path('levels/<int:pk>/edit/', views.level_edit, name='level_edit'),
    path('levels/<int:pk>/delete/', views.level_delete, name='level_delete'),

    # ============================================================
    # Bulk Tools
    # ============================================================
    path('import/', views.bulk_import, name='bulk_import'),
    path('qr/<str:employee_id>.svg', views.qr_employee_svg, name='qr_employee_svg'),
    
]