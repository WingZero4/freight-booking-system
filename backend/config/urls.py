from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.permissions import IsAdminUser
from drf_spectacular.views import (
    SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView,
)
from rest_framework.throttling import AnonRateThrottle
from rest_framework_simplejwt.views import (
    TokenObtainPairView, TokenRefreshView,
)
from bookings.registration_views import register


class _JWTObtainThrottle(AnonRateThrottle):
    scope = 'token_obtain'

urlpatterns = [
    # Admin logout must come before admin/ to intercept it (POST only for CSRF safety)
    path('admin/logout/', auth_views.LogoutView.as_view(
        http_method_names=['post'], next_page='/admin/login/'
    )),
    path('admin/', admin.site.urls),
    path('api/v1/', include('bookings.api_urls')),
    # JWT endpoints at distinct path (api/v1/token/ is DRF auth token in api_urls)
    path('api/v1/token/jwt/', TokenObtainPairView.as_view(
        throttle_classes=[_JWTObtainThrottle]), name='token_obtain_pair'),
    path('api/v1/token/jwt/refresh/', TokenRefreshView.as_view(
        throttle_classes=[_JWTObtainThrottle]), name='token_refresh'),
    path('api/schema/', SpectacularAPIView.as_view(permission_classes=[IsAdminUser]), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema', permission_classes=[IsAdminUser]), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema', permission_classes=[IsAdminUser]), name='redoc'),
    path('', include('bookings.urls')),
    path('register/', register, name='register'),
    path('login/', auth_views.LoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/login/'), name='logout'),

    # Password change (for logged-in users)
    path('password_change/',
         auth_views.PasswordChangeView.as_view(
             template_name='registration/password_change_form.html'
         ), name='password_change'),
    path('password_change/done/',
         auth_views.PasswordChangeDoneView.as_view(
             template_name='registration/password_change_done.html'
         ), name='password_change_done'),

    # Password reset (for forgotten passwords)
    path('password_reset/',
         auth_views.PasswordResetView.as_view(
             template_name='registration/password_reset_form.html'
         ), name='password_reset'),
    path('password_reset/done/',
         auth_views.PasswordResetDoneView.as_view(
             template_name='registration/password_reset_done.html'
         ), name='password_reset_done'),
    path('reset/<uidb64>/<token>/',
         auth_views.PasswordResetConfirmView.as_view(
             template_name='registration/password_reset_confirm.html'
         ), name='password_reset_confirm'),
    path('reset/done/',
         auth_views.PasswordResetCompleteView.as_view(
             template_name='registration/password_reset_complete.html'
         ), name='password_reset_complete'),
]

# Serve uploaded files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
