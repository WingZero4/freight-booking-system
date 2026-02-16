from django.urls import path
from . import views, import_views, user_management_views, report_views, pdf_views

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
    path('bookings/<int:booking_id>/arrived/',
         views.ops_mark_arrived, name='ops_mark_arrived'),
    path('bookings/<int:booking_id>/complete/',
         views.ops_complete_booking, name='ops_complete_booking'),
    path('bookings/<int:booking_id>/milestones/add/',
         views.ops_record_milestone, name='ops_record_milestone'),
    path('bookings/<int:booking_id>/milestones/<int:milestone_id>/delete/',
         views.ops_delete_milestone, name='ops_delete_milestone'),

    # Registration approval (staff)
    path('ops/registrations/', views.ops_pending_registrations, name='ops_pending_registrations'),
    path('ops/registrations/<int:profile_id>/', views.ops_approve_registration, name='ops_approve_registration'),

    # User management (staff)
    path('ops/users/', user_management_views.ops_user_list, name='ops_user_list'),
    path('ops/users/add/staff/', user_management_views.ops_user_add_staff, name='ops_user_add_staff'),
    path('ops/users/add/customer/', user_management_views.ops_user_add_customer, name='ops_user_add_customer'),
    path('ops/users/<int:user_id>/edit/', user_management_views.ops_user_edit, name='ops_user_edit'),
    path('ops/users/<int:user_id>/toggle-active/', user_management_views.ops_user_toggle_active, name='ops_user_toggle_active'),

    # Notifications
    path('notifications/', views.notification_list, name='notification_list'),
    path('notifications/<int:notification_id>/read/',
         views.notification_mark_read, name='notification_mark_read'),
    path('notifications/mark-all-read/',
         views.notification_mark_all_read, name='notification_mark_all_read'),

    # Booking Templates
    path('templates/', views.template_list, name='template_list'),
    path('templates/<int:template_id>/create/', views.booking_create_from_template, name='booking_create_from_template'),
    path('templates/<int:template_id>/delete/', views.template_delete, name='template_delete'),
    path('bookings/<int:booking_id>/save-template/', views.template_save, name='template_save'),

    # Profile
    path('profile/', views.profile_edit, name='profile_edit'),

    # Reports (staff)
    path('ops/reports/', report_views.ops_reports, name='ops_reports'),

    # Bulk Operations (staff)
    path('bookings/bulk-action/', views.ops_bulk_action, name='ops_bulk_action'),

    # Booking CRUD (export/import MUST come before <int:booking_id>)
    path('bookings/', views.booking_list, name='booking_list'),
    path('bookings/export/', views.booking_export_csv, name='booking_export_csv'),
    path('bookings/import/', import_views.booking_import, name='booking_import'),
    path('bookings/import/preview/', import_views.booking_import_preview, name='booking_import_preview'),
    path('bookings/import/confirm/', import_views.booking_import_confirm, name='booking_import_confirm'),
    path('bookings/create/', views.booking_create, name='booking_create'),
    path('bookings/<int:booking_id>/', views.booking_detail, name='booking_detail'),
    path('bookings/<int:booking_id>/edit/', views.booking_edit, name='booking_edit'),
    path('bookings/<int:booking_id>/submit/', views.booking_submit, name='booking_submit'),
    path('bookings/<int:booking_id>/cancel/', views.booking_cancel, name='booking_cancel'),
    path('bookings/<int:booking_id>/resubmit/', views.booking_resubmit, name='booking_resubmit'),
    path('bookings/<int:booking_id>/clone/', views.booking_clone, name='booking_clone'),

    # PDF downloads
    path('bookings/<int:booking_id>/pdf/confirmation/',
         pdf_views.booking_confirmation_pdf, name='booking_confirmation_pdf'),
    path('bookings/<int:booking_id>/pdf/shipping-advice/',
         pdf_views.shipping_advice_pdf, name='shipping_advice_pdf'),

    # Documents
    path('bookings/<int:booking_id>/documents/upload/',
         views.booking_document_upload, name='booking_document_upload'),
    path('bookings/<int:booking_id>/documents/<int:document_id>/delete/',
         views.booking_document_delete, name='booking_document_delete'),
    path('bookings/<int:booking_id>/documents/<int:document_id>/download/',
         views.booking_document_download, name='booking_document_download'),

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
