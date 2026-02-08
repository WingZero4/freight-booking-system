from django.urls import path
from . import views

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),

    # Operations (Staff)
    path('ops/', views.ops_dashboard, name='ops_dashboard'),
    path('bookings/<int:booking_id>/confirm/',
         views.ops_booking_confirm, name='ops_booking_confirm'),
    path('bookings/<int:booking_id>/reject/',
         views.ops_booking_reject, name='ops_booking_reject'),
    path('bookings/<int:booking_id>/carrier/',
         views.ops_carrier_details, name='ops_carrier_details'),
    path('bookings/<int:booking_id>/in-transit/',
         views.ops_mark_in_transit, name='ops_mark_in_transit'),
    path('bookings/<int:booking_id>/complete/',
         views.ops_complete_booking, name='ops_complete_booking'),

    # Booking CRUD (export MUST come before <int:booking_id>)
    path('bookings/', views.booking_list, name='booking_list'),
    path('bookings/export/', views.booking_export_csv, name='booking_export_csv'),
    path('bookings/create/', views.booking_create, name='booking_create'),
    path('bookings/<int:booking_id>/', views.booking_detail, name='booking_detail'),
    path('bookings/<int:booking_id>/edit/', views.booking_edit, name='booking_edit'),
    path('bookings/<int:booking_id>/submit/', views.booking_submit, name='booking_submit'),
    path('bookings/<int:booking_id>/cancel/', views.booking_cancel, name='booking_cancel'),
    path('bookings/<int:booking_id>/clone/', views.booking_clone, name='booking_clone'),

    # Documents
    path('bookings/<int:booking_id>/documents/upload/',
         views.booking_document_upload, name='booking_document_upload'),
    path('bookings/<int:booking_id>/documents/<int:document_id>/delete/',
         views.booking_document_delete, name='booking_document_delete'),

    # Booking party assignment
    path('bookings/<int:booking_id>/parties/add/',
         views.booking_party_add, name='booking_party_add'),
    path('bookings/<int:booking_id>/parties/<int:booking_party_id>/remove/',
         views.booking_party_remove, name='booking_party_remove'),

    # Address book (parties)
    path('parties/', views.party_list, name='party_list'),
    path('parties/create/', views.party_create, name='party_create'),
    path('parties/<int:party_id>/edit/', views.party_edit, name='party_edit'),
    path('parties/<int:party_id>/delete/', views.party_delete, name='party_delete'),
]
