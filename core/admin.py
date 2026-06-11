from django.contrib import admin
from .models import Product, Purchase, Sale, Expense, Category


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['path', 'name', 'updated_at']
    search_fields = ['path', 'name', 'note']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        'sku', 'name', 'category', 'unit',
        'stock_quantity', 'alert_threshold',
        'price_sell', 'price_buy_latest',
        'stock_status_label'
    ]
    search_fields = ['sku', 'name', 'category', 'supplier_name']
    readonly_fields = ['sku', 'stock_quantity', 'created_at', 'updated_at']


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = [
        'date', 'product', 'supplier_name',
        'quantity', 'unit_price', 'total_amount'
    ]
    search_fields = ['product__name', 'supplier_name']
    readonly_fields = ['total_amount', 'created_at', 'updated_at']

    def delete_model(self, request, obj):
        product = obj.product
        product.stock_quantity -= obj.quantity
        product.save()
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            product = obj.product
            product.stock_quantity -= obj.quantity
            product.save()
        super().delete_queryset(request, queryset)

@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = [
        'date', 'product', 'customer_name',
        'quantity', 'unit_price', 'total_amount'
    ]
    search_fields = ['product__name', 'customer_name']
    readonly_fields = ['total_amount', 'created_at', 'updated_at']

    def delete_model(self, request, obj):
        product = obj.product
        product.stock_quantity += obj.quantity
        product.save()
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            product = obj.product
            product.stock_quantity += obj.quantity
            product.save()
        super().delete_queryset(request, queryset)
        

@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ['date', 'expense_type', 'amount', 'estimated_lifetime_months']
    readonly_fields = ['created_at', 'updated_at']
