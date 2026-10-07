from django.urls import path
from books import views

urlpatterns = [
    path('', views.home), path('login/', views.auth_page), path('signup/', views.auth_page, {'signup':True}), path('logout/',views.logout_page),
    path('api/bootstrap/',views.bootstrap), path('api/dashboard/',views.dashboard), path('api/opening/',views.opening),
    path('api/masters/<str:collection>/',views.master_create), path('api/vouchers/',views.vouchers),
    path('api/vouchers/<uuid:voucher_id>/',views.voucher_detail), path('api/vouchers/<uuid:voucher_id>/<str:action>/',views.voucher_detail),
    path('api/ledger/',views.ledger), path('api/inventory/',views.inventory), path('api/audit/',views.audit), path('api/export/ledger.csv',views.ledger_export),
    path('api/export/inventory.csv',views.inventory_export), path('api/export/vouchers.csv',views.voucher_export),
]
