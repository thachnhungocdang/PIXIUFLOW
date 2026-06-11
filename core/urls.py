from django.urls import path
from . import views

urlpatterns = [
    path('', views.landing_view, name='landing'),
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('onboarding/', views.onboarding_welcome_view, name='onboarding_welcome'),
    path('onboarding/opening-stock/', views.opening_stock_wizard_view, name='opening_stock_wizard'),
    path('setup/products/', views.setup_products_view, name='setup_products'),

    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('settings/', views.account_settings_view, name='account_settings'),

    path('transactions/create/', views.transaction_create_view, name='transaction_create'),
    path('transactions/bulk-create/', views.bulk_transaction_create_view, name='bulk_transaction_create'),

    path('products/create/', views.product_create_view, name='product_create'),
    path('products/preview-sku/', views.preview_product_sku, name='preview_product_sku'),
    path('products/delete/<int:pk>/', views.product_delete_view, name='product_delete'),

    path('inventory/', views.inventory_view, name='inventory'),
    path('inventory/products/<int:pk>/inline-update/', views.inventory_inline_update_view, name='inventory_inline_update'),
    path('inventory/categories/bulk-move/', views.inventory_category_bulk_move_view, name='inventory_category_bulk_move'),
    path('inventory/categories/delete/', views.inventory_category_delete_view, name='inventory_category_delete'),
    path('inventory/categories/create/', views.inventory_category_create_view, name='inventory_category_create'),
    path('inventory/categories/rename/', views.inventory_category_rename_view, name='inventory_category_rename'),

    path('sales/create/', views.sale_create_view, name='sale_create'),
    path('sales/create/ajax-new-product/', views.sale_new_product_ajax_view, name='sale_create_ajax_new_product'),

    path('expenses/create/', views.expense_create_view, name='expense_create'),
    path('expenses/create/ajax-new-product/', views.expense_new_product_ajax_view, name='expense_create_ajax_new_product'),

    path('transactions/history/', views.transaction_history_view, name='transaction_history'),
    path('transactions/<str:kind>/<int:pk>/mark-paid/', views.mark_transaction_paid_view, name='transaction_mark_paid'),
    path('transactions/<str:kind>/<int:pk>/extend-due/', views.extend_transaction_due_view, name='transaction_extend_due'),
    path('transactions/sales/<int:pk>/edit/', views.sale_edit_view, name='transaction_sale_edit'),
    path('transactions/sales/<int:pk>/delete/', views.sale_delete_view, name='transaction_sale_delete'),
    path('transactions/purchases/<int:pk>/edit/', views.purchase_edit_view, name='transaction_purchase_edit'),
    path('transactions/purchases/<int:pk>/delete/', views.purchase_delete_view, name='transaction_purchase_delete'),
    path('transactions/expenses/<int:pk>/edit/', views.expense_edit_view, name='transaction_expense_edit'),
    path('transactions/expenses/<int:pk>/delete/', views.expense_delete_view, name='transaction_expense_delete'),

    path('report/', views.report_view, name='report'),
]
