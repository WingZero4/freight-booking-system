from django.urls import path
from . import views

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),

    # Booking CRUD
    path('bookings/', views.booking_list, name='booking_list'),
    path('bookings/create/', views.booking_create, name='booking_create'),
    path('bookings/<int:booking_id>/', views.booking_detail, name='booking_detail'),
    path('bookings/<int:booking_id>/edit/', views.booking_edit, name='booking_edit'),
    path('bookings/<int:booking_id>/submit/', views.booking_submit, name='booking_submit'),
    path('bookings/<int:booking_id>/cancel/', views.booking_cancel, name='booking_cancel'),

    # Documents
    path('bookings/<int:booking_id>/documents/upload/',
         views.booking_document_upload, name='booking_document_upload'),
    path('bookings/<int:booking_id>/documents/<int:document_id>/delete/',
         views.booking_document_delete, name='booking_document_delete'),
]
