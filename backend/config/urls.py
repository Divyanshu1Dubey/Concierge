from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import TokenRefreshView
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from django.http import JsonResponse

from apps.core.views import HealthCheckView, ReadyCheckView, VersionCheckView, serve_widget_js, serve_demo_html, RootIndexView
from apps.users.views import LoginView

def mock_api_view(request, *args, **kwargs):
    return JsonResponse({"count": 0, "next": None, "previous": None, "results": []})

urlpatterns = [
    # Gateway Root
    path('', RootIndexView.as_view(), name='root-index'),

    # Admin
    path('admin/', admin.site.urls),

    # Health & Diagnostics
    path('health', HealthCheckView.as_view(), name='health'),
    path('health/', HealthCheckView.as_view(), name='health-slash'),
    path('ready', ReadyCheckView.as_view(), name='ready'),
    path('ready/', ReadyCheckView.as_view(), name='ready-slash'),
    path('version', VersionCheckView.as_view(), name='version'),
    path('version/', VersionCheckView.as_view(), name='version-slash'),
    path('api/health/', HealthCheckView.as_view(), name='api-health'),

    # Interactive Demo Page
    path('demo', serve_demo_html, name='demo-html-no-slash'),
    path('demo/', serve_demo_html, name='demo-html'),
    path('test-widget/', serve_demo_html, name='test-widget-html'),

    # Public Widget JS Delivery
    path('widget.js', serve_widget_js, name='widget-script'),
    path('api/widget.js', serve_widget_js, name='api-widget-script'),

    # Authentication (email+password)
    path('api/auth/', include('apps.users.urls')),
    path('api/auth/token/', LoginView.as_view(), name='token_obtain_pair'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/auth/google/', include('allauth.socialaccount.providers.google.urls')),

    # Tenancy & Admin
    path('api/practices/', include('apps.practices.urls')),
    path('api/admin/tenants/', include('apps.practices.urls')),

    # Front Desk & Conversations
    path('api/conversations/', include('apps.conversations.urls')),
    path('api/chat/', include('apps.conversations.urls')),
    path('api/appointments/', include('apps.appointments.urls')),
    path('api/requests/', include('apps.appointments.urls')), # Frontend front-desk alias
    path('api/emails/', include('apps.emails.urls')),
    path('api/dashboard/', include('apps.dashboard.urls')),

    # Public Widget and Hosted Concierge API
    path('api/v1/widget/', include('apps.conversations.urls')),
    path('api/v1/concierge/', include('apps.conversations.urls')),
    path('api/concierge/', include('apps.conversations.urls')),

    # API Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/docs/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # Fallback for undefined endpoints
    re_path(r'^api/.*$', mock_api_view),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    try:
        import debug_toolbar
        urlpatterns += [path('__debug__/', include(debug_toolbar.urls))]
    except ImportError:
        pass
