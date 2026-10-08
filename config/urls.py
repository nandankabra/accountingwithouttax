from django.urls import path
from books import views
from books import account_views
from books.admin import provider_site
from books.company import company
from books.pdf_export import voucher_pdf
from books.licensing import activation_page,activation_api

urlpatterns = [
    path('admin/',provider_site.urls),
    path('company/',company),
    path('activate/',activation_page),
    path('api/activation/',activation_api),
    path('security/',account_views.ChangePassword.as_view()),
    path('password-reset/',account_views.RequestPasswordReset.as_view(),name='password_reset'),
    path('password-reset/sent/',account_views.reset_sent),
    path('password-reset/confirm/<uidb64>/<token>/',account_views.ConfirmPasswordReset.as_view(),name='password_reset_confirm'),
    path('password-reset/complete/',account_views.reset_complete),
    path('', views.home), path('login/', views.auth_page), path('signup/', views.auth_page, {'signup':True}), path('logout/',views.logout_page),
    path('api/bootstrap/',views.bootstrap), path('api/dashboard/',views.dashboard), path('api/opening/',views.opening),
    path('api/masters/<str:collection>/',views.master_create), path('api/vouchers/',views.vouchers),
    path('api/vouchers/<uuid:voucher_id>/pdf/',voucher_pdf),
    path('api/vouchers/<uuid:voucher_id>/',views.voucher_detail), path('api/vouchers/<uuid:voucher_id>/<str:action>/',views.voucher_detail),
    path('api/ledger/',views.ledger), path('api/inventory/',views.inventory), path('api/audit/',views.audit), path('api/export/ledger.csv',views.ledger_export),
    path('api/export/inventory.csv',views.inventory_export), path('api/export/vouchers.csv',views.voucher_export),
]
