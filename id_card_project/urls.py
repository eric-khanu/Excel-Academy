"""
URL configuration for id_card_project.

Routes:
    /admin/         → Django admin panel
    /               → id_cards app (list, detail, edit, print, PDF, settings)
    /favicon.ico    → serves the site favicon from /static/
    /media/*        → user-uploaded files (logos, teacher photos) — dev only
    /static/*       → static assets — dev only

Docs:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView


# ----------------------------------------------------------------------------
# Application routes
# ----------------------------------------------------------------------------
urlpatterns = [
    # Django admin
    path('admin/', admin.site.urls),

    # Main application — all ID card views live under the root path
    path('', include('id_cards.urls')),
    path('students/', include('student.urls', namespace='student')),

    # Favicon — redirect to the static file to avoid 404 noise in the console
    path(
        'favicon.ico',
        RedirectView.as_view(url=settings.STATIC_URL + 'favicon.ico', permanent=True),
    ),
]


# ----------------------------------------------------------------------------
# Development-only: serve media + static files through Django
# (In production, Nginx / WhiteNoise / S3 should handle these.)
# ----------------------------------------------------------------------------
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)