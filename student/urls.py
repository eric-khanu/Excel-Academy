from django.urls import path
from . import views

app_name = 'student'

urlpatterns = [
    # Dashboard
    path('', views.student_list, name='student_list'),

    # CRUD
    path('new/', views.student_create, name='student_create'),
    path('<int:pk>/', views.student_detail, name='student_detail'),
    path('<int:pk>/edit/', views.student_edit, name='student_edit'),
    path('<int:pk>/delete/', views.student_delete, name='student_delete'),

    # Print & PDF
    path('<int:pk>/print/', views.student_print, name='student_print'),
    path('<int:pk>/pdf/', views.student_pdf, name='student_pdf'),
    path('print-all/', views.student_print_all, name='student_print_all'),
    path('pdf-all/', views.student_pdf_all, name='student_pdf_all'),

    # Print tracking
    path('<int:pk>/print-reset/', views.student_print_reset, name='student_print_reset'),
    path('reset-print-counts/', views.reset_all_student_prints, name='reset_all_student_prints'),
        # QR code
    path('qr/<str:admission_number>.svg', views.student_qr_svg, name='student_qr_svg'),
]