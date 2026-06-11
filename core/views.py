from datetime import datetime, timedelta
from decimal import Decimal
import json
from urllib.parse import quote, urlencode

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Sum, Count, Q
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, authenticate, update_session_auth_hash
from django.contrib.auth.models import User
from .models import Product, Purchase, Sale, Expense, OpeningStock, Category
from .forms import AccountPasswordChangeForm, ProductForm, PurchaseForm, SaleForm, ExpenseForm
from .utils import generate_product_sku
from django.db.models.functions import TruncMonth
from django.utils import timezone

UNCATEGORIZED_CATEGORY_LABEL = '\u0043\u0048\u01af\u0041 \u0043\u00d3 \u0044\u0041\u004e\u0048 \u004d\u1ee4\u0043 \u0043\u1ea4\u0050 1'
PAYMENT_WARNING_DAYS = 7
EXPENSE_RATIO_ATTENTION_THRESHOLD = Decimal('75')
EXPENSE_RATIO_LOSS_THRESHOLD = Decimal('100')
EXPENSE_CATEGORY_DOMINANCE_THRESHOLD = Decimal('50')
EXPENSE_SPIKE_MULTIPLIER = Decimal('3')
EXPENSE_DELTA_HIGH_THRESHOLD = Decimal('50')

def for_user(model, user):
    if not user or not user.is_authenticated:
        return model.objects.none()
    return model.objects.filter(user=user)


def expenses_for_user(user):
    expenses = for_user(Expense, user)
    if not user or not user.is_authenticated:
        return expenses

    owner_ids = list(
        Expense.objects.exclude(user__isnull=True)
        .order_by()
        .values_list('user_id', flat=True)
        .distinct()[:2]
    )
    if owner_ids == [user.id]:
        return Expense.objects.filter(Q(user=user) | Q(user__isnull=True))
    return expenses


@login_required
def preview_product_sku(request):
    category = request.GET.get("category", "").strip()
    return JsonResponse({
        "sku": generate_product_sku(request.user, category or "SP"),
    })


def set_user(instance, user):
    if user and user.is_authenticated and not instance.user_id:
        instance.user = user
    return instance


def save_business_profile_from_request(request):
    owner_name = (request.POST.get('owner_name') or '').strip()
    if owner_name and owner_name != 'Tên chủ doanh nghiệp':
        request.session['owner_name'] = owner_name
        if request.user.is_authenticated and request.user.first_name != owner_name:
            request.user.first_name = owner_name
            request.user.save(update_fields=['first_name'])

    business_name = (request.POST.get('biz_name') or '').strip()
    if business_name:
        request.session['business_name'] = business_name


@login_required
def account_settings_view(request):
    password_changed = False
    profile_updated = False
    profile_error = ''
    if request.method == 'POST':
        if request.POST.get('action') == 'update_profile':
            owner_name = (request.POST.get('owner_name') or '').strip()
            if owner_name and owner_name != 'Tên chủ doanh nghiệp':
                save_business_profile_from_request(request)
                profile_updated = True
            else:
                profile_error = 'Vui lòng nhập tên chủ doanh nghiệp.'
            form = AccountPasswordChangeForm(request.user)
        else:
            form = AccountPasswordChangeForm(request.user, request.POST)
            if form.is_valid():
                user = form.save()
                update_session_auth_hash(request, user)
                password_changed = True
                form = AccountPasswordChangeForm(request.user)
    else:
        form = AccountPasswordChangeForm(request.user)

    return render(request, 'core/account_settings.html', {
        'password_form': form,
        'password_changed': password_changed,
        'profile_updated': profile_updated,
        'profile_error': profile_error,
    })


def month_start_date(value):
    return datetime(value.year, value.month, 1).date()


def add_months_date(value, months):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return datetime(year, month, 1).date()


def month_count_between(start, end):
    if not start or not end or end < start:
        return 0
    return (end.year - start.year) * 12 + end.month - start.month + 1


def recognized_expense_summary(start_date=None, end_date=None, user=None):
    period_end = end_date or timezone.now().date()
    period_start_month = month_start_date(start_date) if start_date else None
    period_end_month = month_start_date(period_end)
    total = Decimal('0')
    by_type = {}
    by_month = {}

    expenses = expenses_for_user(user) if user is not None else Expense.objects.all()
    for expense in expenses:
        amount = Decimal(expense.amount or 0)
        if expense.estimated_lifetime_months:
            depreciation_start = month_start_date(expense.date)
            depreciation_end = add_months_date(depreciation_start, expense.estimated_lifetime_months - 1)
            overlap_start = max(depreciation_start, period_start_month or depreciation_start)
            overlap_end = min(depreciation_end, period_end_month)
            months = month_count_between(overlap_start, overlap_end)
            if months <= 0:
                continue
            monthly_amount = amount / Decimal(expense.estimated_lifetime_months)
            recognized_amount = monthly_amount * months
            cursor = overlap_start
            while cursor <= overlap_end:
                key = cursor.strftime('%Y-%m')
                by_month[key] = by_month.get(key, Decimal('0')) + monthly_amount
                cursor = add_months_date(cursor, 1)
        else:
            if start_date and expense.date < start_date:
                continue
            if end_date and expense.date > end_date:
                continue
            recognized_amount = amount
            key = month_start_date(expense.date).strftime('%Y-%m')
            by_month[key] = by_month.get(key, Decimal('0')) + amount

        total += recognized_amount
        by_type[expense.expense_type] = by_type.get(expense.expense_type, Decimal('0')) + recognized_amount

    return {
        'total': total,
        'by_type': by_type,
        'by_month': by_month,
    }


def cogs_summary(start_date=None, end_date=None, user=None):
    """
    COGS = gia von hang da ban trong ky.
    Lay tu sale.cogs_amount da luu tai thoi diem ban; khong dung Purchase
    vi nhap hang la ton kho/tai san cho den khi hang duoc ban.
    """
    qs = for_user(Sale, user) if user is not None else Sale.objects.all()
    if start_date:
        qs = qs.filter(date__gte=start_date)
    if end_date:
        qs = qs.filter(date__lte=end_date)

    total = qs.aggregate(total=Sum('cogs_amount'))['total'] or Decimal('0')
    by_month = {}
    for item in qs.annotate(month=TruncMonth('date')).values('month').annotate(total=Sum('cogs_amount')):
        if not item['month']:
            continue
        by_month[item['month'].strftime('%Y-%m')] = item['total'] or Decimal('0')

    return {'total': total, 'by_month': by_month}


def cash_flow_summary(start_date=None, end_date=None, user=None):
    def in_period(value):
        if start_date and value < start_date:
            return False
        if end_date and value > end_date:
            return False
        return True

    income = Decimal('0')
    purchase_out = Decimal('0')
    expense_out = Decimal('0')
    income_by_date = {}
    purchase_by_date = {}
    expense_by_date = {}

    sales = (for_user(Sale, user) if user is not None else Sale.objects.all()).select_related('product')
    purchases = (for_user(Purchase, user) if user is not None else Purchase.objects.all()).select_related('product')
    expenses = for_user(Expense, user) if user is not None else Expense.objects.all()

    for sale in sales.exclude(payment_method=Sale.PAYMENT_METHOD_DEBT):
        cash_date = sale.payment_date or sale.date
        if not in_period(cash_date):
            continue
        amount = sale.total_amount or Decimal('0')
        income += amount
        income_by_date[cash_date] = income_by_date.get(cash_date, Decimal('0')) + amount

    for purchase in purchases.exclude(payment_method=Purchase.PAYMENT_METHOD_DEBT):
        cash_date = purchase.payment_date or purchase.date
        if not in_period(cash_date):
            continue
        amount = purchase.total_amount or Decimal('0')
        purchase_out += amount
        purchase_by_date[cash_date] = purchase_by_date.get(cash_date, Decimal('0')) + amount

    for expense in expenses.exclude(payment_method=Expense.PAYMENT_METHOD_DEBT):
        cash_date = expense.payment_date or expense.date
        if not in_period(cash_date):
            continue
        amount = expense.amount or Decimal('0')
        expense_out += amount
        expense_by_date[cash_date] = expense_by_date.get(cash_date, Decimal('0')) + amount

    outflow = purchase_out + expense_out
    return {
        'income': income,
        'purchase_out': purchase_out,
        'expense_out': expense_out,
        'outflow': outflow,
        'net': income - outflow,
        'income_by_date': income_by_date,
        'purchase_by_date': purchase_by_date,
        'expense_by_date': expense_by_date,
    }


def purchase_payment_summary(purchases, today=None):
    today = today or timezone.now().date()
    purchase_list = list(purchases)
    debt_purchases = [
        purchase for purchase in purchase_list
        if purchase.payment_method == Purchase.PAYMENT_METHOD_DEBT
    ]
    if not debt_purchases:
        latest = purchase_list[0] if purchase_list else None
        return {
            'key': latest.payment_method if latest else 'none',
            'label': 'Đã thanh toán' if latest else 'Chưa theo dõi',
            'due_date': None,
        }

    debt_purchases.sort(key=lambda purchase: purchase.payment_due_date or today)
    due_purchase = debt_purchases[0]
    due_date = due_purchase.payment_due_date
    if due_date and due_date < today:
        key = 'overdue'
        label = 'Quá hạn thanh toán'
    elif due_date and due_date <= today + timedelta(days=PAYMENT_WARNING_DAYS):
        key = 'due_soon'
        label = 'Sắp đến hạn'
    else:
        key = 'debt'
        label = 'Đang theo dõi nợ'

    return {
        'key': key,
        'label': label,
        'due_date': due_date,
    }


def transaction_payment_status(payment_method, payment_due_date, today=None):
    today = today or timezone.now().date()
    if payment_method != Purchase.PAYMENT_METHOD_DEBT:
        return {
            'key': 'paid',
            'label': 'Đã thanh toán',
            'days_remaining': None,
        }
    if not payment_due_date:
        return {
            'key': 'unpaid',
            'label': 'Chưa thanh toán',
            'days_remaining': None,
        }
    days_remaining = (payment_due_date - today).days
    if days_remaining < 0:
        suffix = f'Quá hạn {abs(days_remaining)} ngày'
        key = 'overdue'
    elif days_remaining == 0:
        suffix = 'Đến hạn hôm nay'
        key = 'due_today'
    else:
        suffix = f'Còn {days_remaining} ngày'
        key = 'unpaid'
    return {
        'key': key,
        'label': f'Chưa thanh toán - {suffix}',
        'days_remaining': days_remaining,
    }


def payment_warning_days(request):
    try:
        value = int(request.session.get('payment_warning_days', PAYMENT_WARNING_DAYS))
    except (TypeError, ValueError):
        value = PAYMENT_WARNING_DAYS
    return max(0, min(value, 60))


def build_payment_alerts(warning_days=None, limit=None, user=None):
    today = timezone.now().date()
    warning_days = PAYMENT_WARNING_DAYS if warning_days is None else warning_days
    payment_warning_until = today + timedelta(days=warning_days)
    customer_alerts = []
    supplier_alerts = []

    sales = (for_user(Sale, user) if user is not None else Sale.objects.all()).select_related('product')
    purchases = (for_user(Purchase, user) if user is not None else Purchase.objects.all()).select_related('product')
    expenses = for_user(Expense, user) if user is not None else Expense.objects.all()

    customer_debt_sales = sales.filter(
        payment_method=Sale.PAYMENT_METHOD_DEBT
    ).filter(Q(payment_due_date__isnull=True) | Q(payment_due_date__lte=payment_warning_until))
    for sale in customer_debt_sales.order_by('payment_due_date', '-created_at'):
        status = transaction_payment_status(sale.payment_method, sale.payment_due_date, today)
        customer_alerts.append({
            'kind': 'sale',
            'id': sale.id,
            'title': sale.customer_name or 'Khách lẻ',
            'detail': sale.product.name,
            'subtitle': sale.product.name,
            'due_date': sale.payment_due_date,
            'amount': sale.total_amount,
            'status': status,
            'url': f"/transactions/history/?type=income&q={quote(sale.product.sku)}",
        })

    purchase_payment_alerts = purchases.filter(
        payment_method=Purchase.PAYMENT_METHOD_DEBT
    ).filter(Q(payment_due_date__isnull=True) | Q(payment_due_date__lte=payment_warning_until))
    for purchase in purchase_payment_alerts.order_by('payment_due_date', '-created_at'):
        status = transaction_payment_status(purchase.payment_method, purchase.payment_due_date, today)
        supplier_alerts.append({
            'kind': 'purchase',
            'id': purchase.id,
            'title': purchase.supplier_name or 'Nhà cung cấp',
            'detail': purchase.product.name,
            'subtitle': purchase.product.name,
            'due_date': purchase.payment_due_date,
            'amount': purchase.total_amount,
            'status': status,
            'url': f"/transactions/history/?type=purchase&q={quote(purchase.product.name)}",
        })

    expense_payment_alerts = expenses.filter(
        payment_method=Expense.PAYMENT_METHOD_DEBT
    ).filter(Q(payment_due_date__isnull=True) | Q(payment_due_date__lte=payment_warning_until))
    for expense in expense_payment_alerts.order_by('payment_due_date', '-created_at'):
        status = transaction_payment_status(expense.payment_method, expense.payment_due_date, today)
        supplier_alerts.append({
            'kind': 'expense',
            'id': expense.id,
            'title': expense.get_expense_type_display(),
            'detail': expense.note or 'Chi phí khác',
            'subtitle': expense.note or 'Chi phí khác',
            'due_date': expense.payment_due_date,
            'amount': expense.amount,
            'status': status,
            'url': f"/transactions/history/?type=expense&q=CP-{expense.id:03d}",
        })

    customer_alerts = sorted(customer_alerts, key=lambda item: (item['due_date'] or today, item['title']))
    supplier_alerts = sorted(supplier_alerts, key=lambda item: (item['due_date'] or today, item['title']))
    supplier_debt_count = len({item['title'] for item in supplier_alerts})
    if limit:
        customer_alerts = customer_alerts[:limit]
        supplier_alerts = supplier_alerts[:limit]
    return {
        'customer_payment_alerts': customer_alerts,
        'supplier_payment_alerts': supplier_alerts,
        'supplier_debt_count': supplier_debt_count,
    }


def landing_view(request):
    return render(request, "core/landing.html")

def signup_view(request):
    errors = []
    if request.method == "POST":
        email_or_phone = (request.POST.get('phone_email') or '').strip()
        password1 = request.POST.get('password1') or ''
        password2 = request.POST.get('password2') or ''

        if not email_or_phone:
            errors.append('Vui lòng nhập email hoặc số điện thoại.')
        if not password1 or not password2:
            errors.append('Vui lòng nhập mật khẩu và xác nhận mật khẩu.')
        elif password1 != password2:
            errors.append('Mật khẩu xác nhận không khớp.')

        if not errors:
            if User.objects.filter(username__iexact=email_or_phone).exists():
                errors.append('Tài khoản này đã tồn tại. Vui lòng đăng nhập.')

        if not errors:
            user = User.objects.create_user(
                username=email_or_phone,
                email=email_or_phone,
                password=password1
            )
            login(request, user)
            save_business_profile_from_request(request)
            request.session['onboarding_started'] = True
            return redirect('dashboard')

    return render(request, "core/signup.html", {'errors': errors})

def login_view(request):
    if request.method == "POST":
        username = (request.POST.get('username') or '').strip()
        password = request.POST.get('password') or ''
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        return render(request, "core/login.html", {'form': None, 'login_error': True})
    return render(request, "core/login.html")


def onboarding_welcome_view(request):
    return redirect('dashboard')


def opening_stock_wizard_view(request):
    return redirect('setup_products')


def setup_products_view(request):
    rows = []
    errors = []
    user_products = for_user(Product, request.user).filter(is_active=True).order_by('name')
    user_sales = for_user(Sale, request.user)
    user_purchases = for_user(Purchase, request.user)
    user_expenses = for_user(Expense, request.user)
    user_opening_stocks = for_user(OpeningStock, request.user)
    has_transactions = user_sales.exists() or user_purchases.exists() or user_expenses.exists()
    has_opening_stock = user_opening_stocks.exists()

    if request.method == 'POST':
        if request.POST.get('action') == 'skip':
            return redirect('dashboard')

        product_ids = request.POST.getlist('product_id[]')
        names = request.POST.getlist('product_name[]')
        categories = request.POST.getlist('category[]')
        units = request.POST.getlist('unit[]')
        sell_prices = request.POST.getlist('price_sell[]')
        unit_costs = request.POST.getlist('estimated_unit_cost[]')
        quantities = request.POST.getlist('quantity[]')
        alert_thresholds = request.POST.getlist('alert_threshold[]')
        confirmations = request.POST.getlist('confirm_opening_change[]')
        delete_opening_flags = request.POST.getlist('delete_opening_stock[]')
        max_rows = max(
            len(product_ids), len(names), len(categories), len(units), len(sell_prices),
            len(unit_costs), len(quantities), len(alert_thresholds), len(confirmations),
            len(delete_opening_flags), 0
        )

        for index in range(max_rows):
            row = {
                'product_id': product_ids[index].strip() if index < len(product_ids) else '',
                'product_name': names[index].strip() if index < len(names) else '',
                'category': categories[index].strip() if index < len(categories) else '',
                'unit': units[index].strip() if index < len(units) else '',
                'price_sell': sell_prices[index].strip() if index < len(sell_prices) else '',
                'estimated_unit_cost': unit_costs[index].strip() if index < len(unit_costs) else '',
                'quantity': quantities[index].strip() if index < len(quantities) else '',
                'alert_threshold': alert_thresholds[index].strip() if index < len(alert_thresholds) else '',
                'confirm_opening_change': confirmations[index] if index < len(confirmations) else '0',
                'delete_opening_stock': delete_opening_flags[index] if index < len(delete_opening_flags) else '0',
            }

            if not row['product_name']:
                row.update({
                    'product_id': '',
                    'category': '',
                    'unit': '',
                    'price_sell': '',
                    'estimated_unit_cost': '',
                    'quantity': '',
                    'alert_threshold': '',
                    'confirm_opening_change': '0',
                    'delete_opening_stock': '0',
                    'has_product_transactions': False,
                    'has_opening_stock': False,
                })
                rows.append(row)
                continue

            rows.append(row)

            row_label = f"Dòng {index + 1}"
            product = None
            if row['product_id'].isdigit():
                product = user_products.filter(pk=row['product_id']).first()
                if not product:
                    errors.append(f"{row_label}: Sản phẩm không hợp lệ.")
                    continue
            else:
                product = user_products.filter(name__iexact=row['product_name']).first()
                if product:
                    row['product_id'] = str(product.id)
            row['has_product_transactions'] = has_transactions
            row['has_opening_stock'] = bool(product) and user_opening_stocks.filter(product=product).exists()
            existing_opening_stocks = list(user_opening_stocks.filter(product=product)) if product else []

            if row['delete_opening_stock'] == '1':
                if not existing_opening_stocks:
                    errors.append(f"{row_label}: Sản phẩm này chưa có hàng ban đầu để xóa.")
                    continue
                if has_transactions and row['confirm_opening_change'] != '1':
                    errors.append(f"{row_label}: Xác nhận cảnh báo trước khi xóa hàng ban đầu.")
                    continue
                row['product'] = product
                row['existing_opening_stocks'] = existing_opening_stocks
                row['delete_opening_stock_value'] = True
                continue

            if not row['category']:
                errors.append(f"{row_label}: Nhập danh mục sản phẩm.")
                continue

            try:
                price_sell = Decimal(str(row['price_sell'] or '0').replace('.', '').replace(',', ''))
            except Exception:
                errors.append(f"{row_label}: Giá bán không hợp lệ.")
                continue
            if price_sell <= 0:
                errors.append(f"{row_label}: Giá bán phải lớn hơn 0.")
                continue

            try:
                quantity = int(row['quantity'] or '0')
            except ValueError:
                errors.append(f"{row_label}: Tồn kho ban đầu không hợp lệ.")
                continue
            if quantity <= 0:
                errors.append(
                    f"{row_label}: Màn này chỉ dùng để khai báo hàng đã có sẵn. Vui lòng nhập tồn kho ban đầu lớn hơn 0, "
                    "hoặc dùng Thêm sản phẩm nếu sản phẩm chưa có hàng."
                )
                continue

            try:
                estimated_unit_cost = Decimal(str(row['estimated_unit_cost'] or '0').replace('.', '').replace(',', ''))
            except Exception:
                errors.append(f"{row_label}: Giá vốn ước tính không hợp lệ.")
                continue
            if estimated_unit_cost <= 0:
                errors.append(f"{row_label}: Giá vốn ước tính phải lớn hơn 0.")
                continue

            try:
                alert_threshold = int(row['alert_threshold'] or '10')
            except ValueError:
                errors.append(f"{row_label}: Ngưỡng cảnh báo không hợp lệ.")
                continue
            if alert_threshold < 0:
                errors.append(f"{row_label}: Ngưỡng cảnh báo không được âm.")
                continue

            current_quantity = sum(stock.quantity for stock in existing_opening_stocks)
            current_cost = (
                existing_opening_stocks[0].estimated_unit_cost
                if existing_opening_stocks else Decimal('0')
            )
            opening_changed = (
                quantity != current_quantity
                or ((quantity > 0 or current_quantity > 0) and estimated_unit_cost != current_cost)
            )
            if has_transactions and opening_changed and row['confirm_opening_change'] != '1':
                errors.append(
                    f"{row_label}: Xác nhận cảnh báo trước khi lưu hoặc sửa hàng ban đầu."
                )
                continue

            row['product'] = product
            row['unit_value'] = row['unit'] or 'cái'
            row['price_sell_value'] = price_sell
            row['quantity_value'] = quantity
            row['estimated_unit_cost_value'] = estimated_unit_cost
            row['alert_threshold_value'] = alert_threshold
            row['existing_opening_stocks'] = existing_opening_stocks
            row['delete_opening_stock_value'] = False

        valid_rows = [
            row for row in rows
            if row.get('product_name') and ('quantity_value' in row or row.get('delete_opening_stock_value'))
        ]
        if not any(row.get('product_name') for row in rows):
            errors.append("Thêm ít nhất một dòng hàng ban đầu.")

        if not errors:
            with transaction.atomic():
                for row in valid_rows:
                    product = row['product']
                    if row['delete_opening_stock_value']:
                        for opening_stock in row['existing_opening_stocks']:
                            opening_stock.delete()
                        continue

                    if product is None:
                        product = Product.objects.create(
                            user=request.user,
                            name=row['product_name'],
                            category=row['category'],
                            unit=row['unit_value'],
                            price_sell=row['price_sell_value'],
                            price_buy_latest=row['estimated_unit_cost_value'],
                            alert_threshold=row['alert_threshold_value'],
                        )
                    else:
                        product.name = row['product_name']
                        product.category = row['category']
                        product.unit = row['unit_value']
                        product.price_sell = row['price_sell_value']
                        product.alert_threshold = row['alert_threshold_value']
                        if row['estimated_unit_cost_value'] > 0:
                            product.price_buy_latest = row['estimated_unit_cost_value']
                        product.save()

                    create_category_path(row['category'], user=request.user)
                    existing_opening_stocks = row['existing_opening_stocks']
                    if existing_opening_stocks:
                        opening_stock = existing_opening_stocks[0]
                        opening_stock.quantity = row['quantity_value']
                        opening_stock.estimated_unit_cost = row['estimated_unit_cost_value']
                        opening_stock.save()
                        for extra_stock in existing_opening_stocks[1:]:
                            extra_stock.delete()
                    else:
                        OpeningStock.objects.create(
                            user=request.user,
                            product=product,
                            quantity=row['quantity_value'],
                            estimated_unit_cost=row['estimated_unit_cost_value'],
                            note='Hàng ban đầu khai báo khi thiết lập sản phẩm.',
                        )

            return redirect('dashboard')

    if not rows and request.method != 'POST':
        for opening_stock in user_opening_stocks.select_related('product').order_by('product__name', 'id'):
            product = opening_stock.product
            rows.append({
                'product_id': str(product.id),
                'product_name': product.name,
                'category': product.category,
                'unit': product.unit,
                'price_sell': product.price_sell,
                'quantity': opening_stock.quantity,
                'estimated_unit_cost': opening_stock.estimated_unit_cost,
                'alert_threshold': product.alert_threshold,
                'has_product_transactions': has_transactions,
                'has_opening_stock': True,
                'delete_opening_stock': '0',
                'confirm_opening_change': '0',
            })

    if not rows:
        rows.extend([
            {
                'product_id': '',
                'product_name': '',
                'category': '',
                'unit': '',
                'price_sell': '',
                'quantity': '',
                'estimated_unit_cost': '',
                'alert_threshold': '',
                'has_product_transactions': False,
                'has_opening_stock': False,
                'delete_opening_stock': '0',
            }
            for _ in range(3)
        ])

    return render(request, 'core/setup_products.html', {
        'rows': rows,
        'errors': errors,
        'has_transactions': has_transactions,
        'has_opening_stock': has_opening_stock,
        'form_submitted': request.method == 'POST' or has_opening_stock,
    })

def inventory_view(request):
    products = for_user(Product, request.user).filter(is_active=True).order_by('name')
    active_products = products
    has_transactions = (
        for_user(Sale, request.user).exists()
        or for_user(Purchase, request.user).exists()
        or for_user(Expense, request.user).exists()
    )
    has_opening_stock = for_user(OpeningStock, request.user).exists()
    products_missing_stock = products.filter(
        stock_quantity=0,
        purchases__isnull=True,
        opening_stocks__isnull=True,
    ).distinct()
    new_product_ids = [
        int(pk) for pk in request.GET.get('new_products', '').split(',')
        if pk.isdigit()
    ]
    created_product_id = request.GET.get('created')
    if created_product_id and created_product_id.isdigit():
        created_product_id = int(created_product_id)
        if created_product_id not in new_product_ids:
            new_product_ids.append(created_product_id)
    else:
        created_product_id = None
    new_products = [
        product for product in for_user(Product, request.user).filter(pk__in=new_product_ids).order_by('name')
        if product_needs_followup(product)
    ]

    low_stock_products = products.filter(
        stock_quantity__lte=F('alert_threshold'),
        stock_quantity__gt=0
    )

    out_of_stock_products = products.filter(stock_quantity=0).filter(
        Q(purchases__isnull=False) | Q(opening_stocks__isnull=False)
    ).distinct()
    adequate_products = active_products.filter(stock_quantity__gt=F('alert_threshold'))
    urgent_products = list(out_of_stock_products[:3]) + list(low_stock_products[:3])

    total_stock = sum(product.stock_quantity for product in active_products)
    inventory_value = sum(
        (product.price_buy_latest or Decimal('0')) * product.stock_quantity
        for product in active_products
    )
    alert_count = out_of_stock_products.count() + low_stock_products.count()
    top_sellers = (
        for_user(Sale, request.user).select_related('product')
        .values('product__name')
        .annotate(quantity=Sum('quantity'), revenue=Sum('total_amount'))
        .order_by('-quantity')[:5]
    )
    category_stats = (
        active_products.values('category')
        .annotate(product_count=Count('id'))
        .order_by('-product_count')
    )
    supplier_stats = (
        for_user(Purchase, request.user).exclude(supplier_name='')
        .values('supplier_name')
        .annotate(total_value=Sum('total_amount'), purchase_count=Count('id'))
        .order_by('-total_value')
    )
    today = timezone.now().date()
    alerts = build_payment_alerts(payment_warning_days(request), limit=4, user=request.user)
    customer_payment_alerts = alerts['customer_payment_alerts']
    supplier_payment_alerts = [item for item in alerts['supplier_payment_alerts'] if item['kind'] == 'purchase']
    other_payable_alerts = [item for item in alerts['supplier_payment_alerts'] if item['kind'] == 'expense'][:3]
    supplier_debt_count = alerts['supplier_debt_count']
    product_rows = []
    category_root = {}
    category_total_count = 0

    def category_node(children, name, level, path):
        if name not in children:
            children[name] = {
                'name': name,
                'level': level,
                'path': path,
                'note': '',
                'is_uncategorized': path == UNCATEGORIZED_CATEGORY_LABEL,
                'product_count': 0,
                'products': [],
                'children': {},
            }
        return children[name]

    def add_category_path(path, note=''):
        parts = [part.strip() for part in (path or '').split('/') if part.strip()]
        if not parts:
            return None
        children = category_root
        path_parts = []
        node = None
        for level, part in enumerate(parts[:4], start=1):
            path_parts.append(part)
            node = category_node(children, part, level, ' / '.join(path_parts))
            children = node['children']
        if node and note:
            node['note'] = note
        return node

    for category in for_user(Category, request.user):
        add_category_path(category.path, category.note)

    for product in products:
        parts = [part.strip() for part in (product.category or '').split('/') if part.strip()]
        if not parts:
            parts = [UNCATEGORIZED_CATEGORY_LABEL]
        parts = parts[:4]
        category_path = ' / '.join(parts)
        has_free_sale = product.sales.filter(unit_price=0).exists()
        sale_price_state = 'priced' if product.price_sell > 0 else ('free' if has_free_sale else 'missing')
        margin = None
        if product.price_buy_latest and product.price_sell and product.price_buy_latest > 0 and product.price_sell > 0:
            margin = round(((product.price_sell - product.price_buy_latest) / product.price_buy_latest) * 100)
        recent_product_purchases = list(product.purchases.order_by('-date', '-created_at')[:3])
        payment_summary = purchase_payment_summary(
            product.purchases.order_by('-date', '-created_at'),
            today,
        )
        if product.alert_threshold > 0:
            stock_bar_percent = min(100, max(4, round((product.stock_quantity / product.alert_threshold) * 100)))
        else:
            stock_bar_percent = 100 if product.stock_quantity > 0 else 4
        product_rows.append({
            'product': product,
            'category_parts': parts,
            'category_path': category_path,
            'sale_price_state': sale_price_state,
            'margin': margin,
            'recent_purchases': recent_product_purchases,
            'payment_summary': payment_summary,
            'stock_bar_percent': stock_bar_percent,
        })
        children = category_root
        path_parts = []
        for level, part in enumerate(parts, start=1):
            path_parts.append(part)
            node = category_node(children, part, level, ' / '.join(path_parts))
            node['product_count'] += 1
            children = node['children']
        node['products'].append(product)

    stock_status_priority = {
        'chua_nhap_hang': 0,
        'het_hang': 1,
        'sap_het': 2,
        'day_du': 3,
    }
    product_rows.sort(key=lambda row: (
        stock_status_priority.get(row['product'].stock_status, 3),
        row['product'].stock_quantity,
        row['product'].name.lower(),
    ))

    category_tree = list(category_root.values())
    category_total_count = len(category_stats)
    category_options = []

    def collect_category_options(nodes):
        for node in nodes:
            category_options.append({
                'name': node['name'],
                'path': node['path'],
                'level': node['level'],
                'is_uncategorized': node.get('is_uncategorized', False),
            })
            collect_category_options(node['children'].values())

    collect_category_options(category_tree)
    category_total_count = len([option for option in category_options if not option.get('is_uncategorized')])

    supplier_rows = []
    for supplier in supplier_stats:
        supplier_rows.append({
            'name': supplier['supplier_name'],
            'purchase_count': supplier['purchase_count'],
            'total_value': supplier['total_value'] or Decimal('0'),
            'payment_summary': purchase_payment_summary(
                for_user(Purchase, request.user).select_related('product')
                .filter(supplier_name=supplier['supplier_name'])
                .order_by('-date', '-created_at'),
                today,
            ),
        })

    equipment_expenses = for_user(Expense, request.user).filter(
        expense_type=Expense.EXPENSE_TYPE_EQUIPMENT
    ).order_by('-date', '-created_at')
    equipment_rows = []
    total_equipment_value = Decimal('0')
    total_equipment_remaining = Decimal('0')
    active_equipment_count = 0

    for expense in equipment_expenses:
        lifetime = expense.estimated_lifetime_months or 1
        months_used = ((today.year - expense.date.year) * 12) + today.month - expense.date.month + 1
        months_used = max(0, min(months_used, lifetime))
        monthly_amount = expense.amount / Decimal(lifetime)
        allocated_amount = min(expense.amount, monthly_amount * Decimal(months_used))
        remaining_amount = max(Decimal('0'), expense.amount - allocated_amount)
        allocated_percent = int(round((allocated_amount / expense.amount) * 100)) if expense.amount else 0
        is_done = months_used >= lifetime or remaining_amount <= 0
        if not is_done:
            active_equipment_count += 1
            total_equipment_remaining += remaining_amount
        total_equipment_value += expense.amount
        note_name = (expense.note or '').strip().splitlines()[0] if expense.note else ''
        if note_name.lower() in {'mua thiết bị', 'mua thiet bi'}:
            note_name = ''
        equipment_rows.append({
            'id': expense.id,
            'name': note_name or f'Thiết bị #{expense.id:03d}',
            'date': expense.date,
            'amount': expense.amount,
            'monthly_amount': monthly_amount,
            'months_used': months_used,
            'lifetime': lifetime,
            'allocated_amount': allocated_amount,
            'allocated_percent': allocated_percent,
            'remaining_amount': remaining_amount,
            'is_done': is_done,
            'status_label': 'Hết khấu hao' if is_done else 'Đang dùng',
        })

    category_margin_map = {}
    for row in product_rows:
        if row['margin'] is None:
            continue
        name = row['category_parts'][0] if row['category_parts'] else 'Hang hoa'
        bucket = category_margin_map.setdefault(name, {'name': name, 'margin_total': 0, 'product_count': 0})
        bucket['margin_total'] += row['margin']
        bucket['product_count'] += 1
    top_profit_categories = sorted(
        [
            {
                'name': item['name'],
                'margin': round(item['margin_total'] / item['product_count']),
                'product_count': item['product_count'],
            }
            for item in category_margin_map.values()
            if item['product_count']
        ],
        key=lambda item: item['margin'],
        reverse=True,
    )[:3]
    top_supplier = supplier_rows[0] if supplier_rows else None
    purchase_product_ids = set(
        for_user(Purchase, request.user)
        .filter(product_id__in=[row['product'].id for row in product_rows])
        .values_list('product_id', flat=True)
    )
    product_details = [
        {
            'id': str(row['product'].id),
            'name': row['product'].name,
            'sku': row['product'].sku,
            'category': row['category_path'] if row['category_path'] != UNCATEGORIZED_CATEGORY_LABEL else '',
            'category_parts': row['category_parts'],
            'unit': row['product'].unit,
            'supplier_name': row['product'].supplier_name,
            'stock_quantity': row['product'].stock_quantity,
            'alert_threshold': row['product'].alert_threshold,
            'price_buy_latest': int(row['product'].price_buy_latest or 0),
            'price_sell': int(row['product'].price_sell or 0),
            'has_purchase_transactions': row['product'].id in purchase_product_ids,
            'can_edit_price_buy_latest': row['product'].id not in purchase_product_ids,
            'sale_price_state': row['sale_price_state'],
            'margin': row['margin'],
            'status': row['product'].stock_status_label,
            'purchase_url': f"/expenses/create/?mode=purchase&product_id={row['product'].id}",
            'edit_url': f"/products/create/?product_id={row['product'].id}",
            'recent_purchases': [
                {
                    'date': purchase.date.strftime('%d/%m/%Y'),
                    'quantity': purchase.quantity,
                    'supplier': purchase.supplier_name or '---',
                    'payment_label': purchase_payment_summary([purchase], today)['label'],
                    'payment_key': purchase_payment_summary([purchase], today)['key'],
                    'payment_due_date': purchase.payment_due_date.strftime('%d/%m/%Y') if purchase.payment_due_date else '',
                }
                for purchase in row['recent_purchases']
            ],
        }
        for row in product_rows
    ]

    return render(request, 'core/inventory.html', {
        'products': products,
        'product_rows': product_rows,
        'product_details': product_details,
        'total_products': active_products.count(),
        'total_stock': total_stock,
        'inventory_value': inventory_value,
        'alert_count': alert_count,
        'products_missing_stock': products_missing_stock,
        'products_missing_stock_count': products_missing_stock.count(),
        'adequate_count': adequate_products.count(),
        'top_sellers': top_sellers,
        'category_stats': category_stats,
        'category_tree': category_tree,
        'category_options': category_options,
        'category_total_count': category_total_count,
        'supplier_stats': supplier_stats,
        'supplier_rows': supplier_rows,
        'equipment_rows': equipment_rows,
        'equipment_total_count': len(equipment_rows),
        'equipment_active_count': active_equipment_count,
        'equipment_total_value': total_equipment_value,
        'equipment_remaining_value': total_equipment_remaining,
        'top_supplier': top_supplier,
        'top_profit_categories': top_profit_categories,
        'customer_payment_alerts': customer_payment_alerts,
        'supplier_payment_alerts': supplier_payment_alerts,
        'supplier_debt_count': supplier_debt_count,
        'other_payable_alerts': other_payable_alerts,
        'today': today,
        'low_stock_products': low_stock_products,
        'out_of_stock_products': out_of_stock_products,
        'urgent_products': urgent_products[:5],
        'new_products': new_products,
        'created_product_id': created_product_id,
        'payment_warning_days': payment_warning_days(request),
        'has_transactions': has_transactions,
        'has_opening_stock': has_opening_stock,
    })

@require_POST
def inventory_inline_update_view(request, pk):
    product = get_object_or_404(for_user(Product, request.user), pk=pk, is_active=True)
    try:
        import json
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Dữ liệu không hợp lệ.'}, status=400)

    field = payload.get('field')
    if field == 'stock_quantity':
        try:
            value = int(payload.get('value'))
        except (TypeError, ValueError):
            return JsonResponse({'ok': False, 'error': 'Giá trị phải là số nguyên.'}, status=400)
        if value < 0:
            return JsonResponse({'ok': False, 'error': 'Giá trị không được âm.'}, status=400)
        product.stock_quantity = value
    elif field == 'alert_threshold':
        try:
            value = int(payload.get('value'))
        except (TypeError, ValueError):
            return JsonResponse({'ok': False, 'error': 'Giá trị phải là số nguyên.'}, status=400)
        if value < 0:
            return JsonResponse({'ok': False, 'error': 'Giá trị không được âm.'}, status=400)
        product.alert_threshold = value
    elif field == 'category':
        product.category = str(payload.get('value') or '').strip()
    elif field == 'supplier_name':
        product.supplier_name = str(payload.get('value') or '').strip()
    elif field == 'product_profile':
        name = str(payload.get('name') or '').strip()
        category = str(payload.get('category') or '').strip()
        unit = str(payload.get('unit') or '').strip()
        supplier_name = str(payload.get('supplier_name') or '').strip()

        def parse_decimal(raw, label, required=False):
            raw = str(raw or '').replace('.', '').replace(',', '').strip()
            if not raw:
                if required:
                    raise ValueError(f'{label} là bắt buộc.')
                return Decimal('0')
            try:
                return Decimal(raw)
            except Exception:
                raise ValueError(f'{label} không hợp lệ.')

        if not name:
            return JsonResponse({'ok': False, 'error': 'Nhập tên sản phẩm.'}, status=400)
        if not category:
            return JsonResponse({'ok': False, 'error': 'Nhập danh mục sản phẩm.'}, status=400)
        if not unit:
            return JsonResponse({'ok': False, 'error': 'Nhập đơn vị tính.'}, status=400)
        try:
            alert_threshold = int(payload.get('alert_threshold') or 0)
            price_sell = parse_decimal(payload.get('price_sell'), 'Giá bán', required=True)
            price_buy_latest = parse_decimal(payload.get('price_buy_latest'), 'Giá vốn', required=True)
        except ValueError as exc:
            return JsonResponse({'ok': False, 'error': str(exc)}, status=400)
        if alert_threshold < 0:
            return JsonResponse({'ok': False, 'error': 'Ngưỡng cảnh báo không được âm.'}, status=400)
        if price_sell <= 0:
            return JsonResponse({'ok': False, 'error': 'Giá bán phải lớn hơn 0.'}, status=400)
        if price_buy_latest < 0:
            return JsonResponse({'ok': False, 'error': 'Giá vốn không được âm.'}, status=400)
        has_purchase_transactions = for_user(Purchase, request.user).filter(product=product).exists()
        if has_purchase_transactions and price_buy_latest != (product.price_buy_latest or Decimal('0')):
            return JsonResponse({
                'ok': False,
                'error': 'Sản phẩm đã có giao dịch nhập kho nên không thể đổi giá vốn tại đây. Hãy sửa phiếu nhập kho trong Lịch sử giao dịch.',
                'purchase_history_url': f"/transactions/history/?type=purchase&q={quote(product.name)}",
            }, status=400)

        duplicate = for_user(Product, request.user).filter(
            name__iexact=name,
            unit__iexact=unit,
            is_active=True,
        ).exclude(pk=product.pk).exists()
        if duplicate:
            return JsonResponse({'ok': False, 'error': 'Đã có sản phẩm cùng tên và đơn vị tính.'}, status=400)

        product.name = name
        product.category = category
        product.unit = unit
        product.supplier_name = supplier_name
        product.alert_threshold = alert_threshold
        product.price_sell = price_sell
        product.price_buy_latest = price_buy_latest
        if category:
            create_category_path(category, user=request.user)
        field = None
    else:
        return JsonResponse({'ok': False, 'error': 'Trường cập nhật không hợp lệ.'}, status=400)

    update_fields = [
        'name', 'category', 'unit', 'supplier_name',
        'alert_threshold', 'price_sell', 'price_buy_latest', 'updated_at'
    ] if field is None else [field, 'updated_at']
    product.save(update_fields=update_fields)
    return JsonResponse({
        'ok': True,
        'id': product.id,
        'name': product.name,
        'category': product.category,
        'unit': product.unit,
        'supplier_name': product.supplier_name,
        'price_sell': product.price_sell,
        'price_buy_latest': product.price_buy_latest,
        'stock_quantity': product.stock_quantity,
        'alert_threshold': product.alert_threshold,
        'stock_status': product.stock_status,
        'stock_status_label': product.stock_status_label,
    })


@require_POST
def inventory_category_bulk_move_view(request):
    try:
        import json
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Du lieu khong hop le.'}, status=400)

    product_ids = payload.get('product_ids') or []
    target_category = str(payload.get('target_category') or '').strip()
    if not product_ids:
        return JsonResponse({'ok': False, 'error': 'Chon it nhat 1 san pham de di chuyen.'}, status=400)
    if not target_category:
        return JsonResponse({'ok': False, 'error': 'Chon danh muc dich.'}, status=400)
    if target_category == UNCATEGORIZED_CATEGORY_LABEL:
        target_category = ''

    updated = for_user(Product, request.user).filter(pk__in=product_ids, is_active=True).update(category=target_category)
    return JsonResponse({'ok': True, 'updated': updated, 'target_category': target_category})


@require_POST
def inventory_category_delete_view(request):
    try:
        import json
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Du lieu khong hop le.'}, status=400)

    category_path = str(payload.get('category_path') or '').strip()
    mode = str(payload.get('mode') or '').strip()
    target_category = str(payload.get('target_category') or '').strip()
    if not category_path:
        return JsonResponse({'ok': False, 'error': 'Thieu danh muc can xoa.'}, status=400)

    products = for_user(Product, request.user).filter(
        Q(category=category_path) | Q(category__startswith=f'{category_path} / '),
        is_active=True,
    )
    affected = products.count()
    if affected and mode not in ('move', 'clear'):
        return JsonResponse({'ok': False, 'error': 'Chon cach xu ly san pham trong danh muc truoc khi xoa.'}, status=400)
    if mode == 'move':
        if affected and not target_category:
            return JsonResponse({'ok': False, 'error': 'Chon danh muc dich.'}, status=400)
        if target_category and (target_category == category_path or target_category.startswith(f'{category_path} / ')):
            return JsonResponse({'ok': False, 'error': 'Danh muc dich khong duoc nam trong danh muc dang xoa.'}, status=400)
        if target_category == UNCATEGORIZED_CATEGORY_LABEL:
            target_category = ''
        if affected:
            products.update(category=target_category)
    elif mode == 'clear':
        products.update(category='')

    for_user(Category, request.user).filter(Q(path=category_path) | Q(path__startswith=f'{category_path} / ')).delete()
    return JsonResponse({'ok': True, 'affected': affected, 'mode': mode})


@require_POST
def inventory_category_create_view(request):
    try:
        import json
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Du lieu khong hop le.'}, status=400)

    name = str(payload.get('name') or '').strip()
    note = str(payload.get('note') or '').strip()
    parent_path = str(payload.get('parent_path') or '').strip()
    product_ids = payload.get('product_ids') or []
    action = str(payload.get('action') or '').strip()

    if not name:
        return JsonResponse({'ok': False, 'error': 'Nhap ten danh muc.'}, status=400)
    if '/' in name:
        return JsonResponse({'ok': False, 'error': 'Ten danh muc khong duoc chua dau /.'}, status=400)
    if parent_path == UNCATEGORIZED_CATEGORY_LABEL:
        parent_path = ''

    parent_parts = [part.strip() for part in parent_path.split('/') if part.strip()]
    if len(parent_parts) >= 4:
        return JsonResponse({'ok': False, 'error': 'Danh muc chi ho tro toi da 4 cap.'}, status=400)

    path = ' / '.join(parent_parts + [name])
    category, created = for_user(Category, request.user).get_or_create(path=path, defaults={'user': request.user, 'name': name, 'note': note})
    if not created:
        category.name = name
        category.note = note
        category.save(update_fields=['name', 'note', 'updated_at'])

    moved = 0
    if action == 'move_selected' and product_ids:
        moved = for_user(Product, request.user).filter(pk__in=product_ids, is_active=True).update(category=path)

    return JsonResponse({
        'ok': True,
        'path': path,
        'created': created,
        'moved': moved,
        'create_product_url': f'/products/create/?category={quote(path)}',
    })


@require_POST
def inventory_category_rename_view(request):
    try:
        import json
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Du lieu khong hop le.'}, status=400)

    old_path = str(payload.get('old_path') or '').strip()
    new_name = str(payload.get('name') or '').strip()
    note = str(payload.get('note') or '').strip()
    if not old_path or old_path == UNCATEGORIZED_CATEGORY_LABEL:
        return JsonResponse({'ok': False, 'error': 'Khong the doi ten nhom chua co danh muc.'}, status=400)
    if not new_name:
        return JsonResponse({'ok': False, 'error': 'Nhap ten danh muc moi.'}, status=400)
    if '/' in new_name:
        return JsonResponse({'ok': False, 'error': 'Ten danh muc khong duoc chua dau /.'}, status=400)

    parent_parts = [part.strip() for part in old_path.split('/') if part.strip()][:-1]
    new_path = ' / '.join(parent_parts + [new_name])
    if new_path != old_path and for_user(Category, request.user).filter(path=new_path).exists():
        return JsonResponse({'ok': False, 'error': 'Da co danh muc cung ten o cap nay.'}, status=400)

    with transaction.atomic():
        for category in for_user(Category, request.user).filter(Q(path=old_path) | Q(path__startswith=f'{old_path} / ')):
            suffix = category.path[len(old_path):]
            category.path = f'{new_path}{suffix}'
            if category.path == new_path:
                category.name = new_name
                category.note = note
            category.save(update_fields=['path', 'name', 'note', 'updated_at'])

        for product in for_user(Product, request.user).filter(Q(category=old_path) | Q(category__startswith=f'{old_path} / '), is_active=True):
            suffix = product.category[len(old_path):]
            product.category = f'{new_path}{suffix}'
            product.save(update_fields=['category', 'updated_at'])

        for_user(Category, request.user).update_or_create(path=new_path, defaults={'user': request.user, 'name': new_name, 'note': note})

    return JsonResponse({'ok': True, 'old_path': old_path, 'path': new_path})

def product_delete_view(request, pk):
    product = get_object_or_404(for_user(Product, request.user), pk=pk)
    product.delete()
    return redirect('inventory')

def product_needs_followup(product):
    if not product:
        return False
    has_stock_source = product.purchases.exists() or product.opening_stocks.exists()
    return not has_stock_source or product.stock_quantity <= 0

def product_category_levels(user=None):
    levels = {1: set(), 2: set(), 3: set(), 4: set()}
    product_qs = for_user(Product, user) if user is not None else Product.objects.all()
    category_qs = for_user(Category, user) if user is not None else Category.objects.all()
    categories = list(product_qs.exclude(category='').values_list('category', flat=True))
    categories += list(category_qs.values_list('path', flat=True))
    for category in categories:
        parts = [part.strip() for part in category.split('/') if part.strip()]
        for index, part in enumerate(parts[:4], start=1):
            levels[index].add(part)
    return [
        {'level': level, 'options': sorted(options)}
        for level, options in levels.items()
    ]

def product_category_tree(user=None):
    tree = {}
    product_qs = for_user(Product, user) if user is not None else Product.objects.all()
    category_qs = for_user(Category, user) if user is not None else Category.objects.all()
    categories = list(product_qs.exclude(category='').values_list('category', flat=True))
    categories += list(category_qs.values_list('path', flat=True))
    for category in categories:
        parts = [part.strip() for part in category.split('/') if part.strip()]
        if not parts:
            continue
        level_1 = parts[0]
        tree.setdefault(level_1, {})
        if len(parts) > 1:
            level_2 = parts[1]
            tree[level_1].setdefault(level_2, {})
            if len(parts) > 2:
                level_3 = parts[2]
                tree[level_1][level_2].setdefault(level_3, [])
                if len(parts) > 3 and parts[3] not in tree[level_1][level_2][level_3]:
                    tree[level_1][level_2][level_3].append(parts[3])
    return tree


def create_category_path(path, note='', user=None):
    if not path:
        return None
    parts = [part.strip() for part in path.split('/') if part.strip()]
    category = None
    for index, part in enumerate(parts):
        current_path = ' / '.join(parts[:index + 1])
        qs = for_user(Category, user) if user is not None else Category.objects.all()
        category, created = qs.get_or_create(
            path=current_path,
            defaults={
                'user': user,
                'name': part,
                'note': note if index == len(parts) - 1 else ''
            }
        )
        if not created and index == len(parts) - 1 and note and not category.note:
            category.note = note
            category.save()
    return category


@require_POST
def sale_new_product_ajax_view(request):
    name = request.POST.get('name', '').strip()
    unit = request.POST.get('unit', '').strip() or 'cái'
    alert_threshold = request.POST.get('alert_threshold', '').strip() or '10'
    category_levels = [request.POST.get(f'category_level_{i}', '').strip() for i in range(1, 5)]
    category_path = ' / '.join([level for level in category_levels if level])
    stock_quantity = request.POST.get('stock_quantity', '').strip() or '0'
    stock_unit_cost = request.POST.get('stock_unit_cost', '').strip() or '0'
    stock_purchase_date = request.POST.get('stock_purchase_date', '').strip() or timezone.now().date().isoformat()
    stock_supplier_name = request.POST.get('stock_supplier_name', '').strip()
    stock_note = request.POST.get('stock_note', '').strip()
    price_sell_value = request.POST.get('price_sell', '').strip() or '0'

    try:
        price_sell = Decimal(str(price_sell_value).replace('.', '').replace(',', ''))
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Giá bán mặc định không hợp lệ.'}, status=400)
    if price_sell <= 0:
        return JsonResponse({'ok': False, 'error': 'Giá bán mặc định phải lớn hơn 0.'}, status=400)

    try:
        alert_threshold_value = int(alert_threshold)
    except ValueError:
        alert_threshold_value = 10

    try:
        stock_quantity_value = int(stock_quantity)
    except ValueError:
        return JsonResponse({'ok': False, 'error': 'Số lượng nhập kho không hợp lệ.'}, status=400)

    try:
        stock_unit_cost_value = Decimal(str(stock_unit_cost).replace('.', '').replace(',', ''))
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Giá vốn không hợp lệ.'}, status=400)

    if stock_quantity_value <= 0:
        return JsonResponse({'ok': False, 'error': 'Số lượng nhập kho phải lớn hơn 0.'}, status=400)
    if stock_unit_cost_value <= 0:
        return JsonResponse({'ok': False, 'error': 'Giá vốn phải lớn hơn 0.'}, status=400)

    try:
        stock_purchase_date_value = datetime.strptime(stock_purchase_date, '%Y-%m-%d').date()
    except ValueError:
        stock_purchase_date_value = timezone.now().date()

    if not name:
        return JsonResponse({'ok': False, 'error': 'Nhập tên sản phẩm mới.'}, status=400)
    if not category_levels[0]:
        return JsonResponse({'ok': False, 'error': 'Nhập danh mục cấp 1 cho sản phẩm mới.'}, status=400)

    with transaction.atomic():
        product = for_user(Product, request.user).filter(name__iexact=name).first()
        created_product = False
        if product is None:
            product = Product.objects.create(
                user=request.user,
                name=name,
                category=category_path,
                unit=unit,
                alert_threshold=max(alert_threshold_value, 0),
                price_sell=price_sell,
            )
            created_product = True
        else:
            if not product.category and category_path:
                product.category = category_path
            if product.unit == '' and unit:
                product.unit = unit
            if product.price_sell <= 0:
                product.price_sell = price_sell
            product.save()

        if category_path:
            create_category_path(category_path, user=request.user)

        Purchase.objects.create(
            user=request.user,
            product=product,
            date=stock_purchase_date_value,
            supplier_name=stock_supplier_name,
            quantity=stock_quantity_value,
            unit_price=stock_unit_cost_value,
            note=stock_note or 'Nhập hàng khi tạo sản phẩm từ giao dịch doanh thu.',
        )

    message = f"Bạn vừa lưu sản phẩm mới '{product.name}'."
    if category_path:
        message += f" Danh mục: {category_path}."

    return JsonResponse({
        'ok': True,
        'product_id': product.id,
        'product_name': product.name,
        'sku': product.sku,
        'message': f"{message} Mã: {product.sku}.",
    })




@require_POST
def expense_new_product_ajax_view(request):
    name = request.POST.get('name', '').strip()
    unit = request.POST.get('unit', '').strip() or 'cái'
    alert_threshold = request.POST.get('alert_threshold', '10').strip()
    price_sell = request.POST.get('price_sell', '0').strip()
    category_levels = [
        request.POST.get('category_level_1', '').strip(),
        request.POST.get('category_level_2', '').strip(),
        request.POST.get('category_level_3', '').strip(),
        request.POST.get('category_level_4', '').strip(),
    ]
    category_path = ' / '.join([level for level in category_levels if level])

    if not name:
        return JsonResponse({'ok': False, 'error': 'Nhập tên sản phẩm mới.'}, status=400)
    if not category_levels[0]:
        return JsonResponse({'ok': False, 'error': 'Nhập danh mục cấp 1 cho sản phẩm mới.'}, status=400)

    try:
        alert_threshold_value = max(int(alert_threshold or '10'), 0)
    except ValueError:
        alert_threshold_value = 10

    try:
        price_sell_value = Decimal(str(price_sell or '0').replace('.', '').replace(',', ''))
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Giá bán mặc định không hợp lệ.'}, status=400)
    if price_sell_value <= 0:
        return JsonResponse({'ok': False, 'error': 'Giá bán mặc định phải lớn hơn 0.'}, status=400)

    with transaction.atomic():
        product = for_user(Product, request.user).filter(name__iexact=name).first()
        created_product = False
        if product is None:
            product = Product.objects.create(
                user=request.user,
                name=name,
                category=category_path,
                unit=unit,
                alert_threshold=alert_threshold_value,
                price_sell=max(price_sell_value, Decimal('0')),
            )
            created_product = True
        else:
            changed = False
            if not product.category and category_path:
                product.category = category_path
                changed = True
            if not product.unit and unit:
                product.unit = unit
                changed = True
            if product.alert_threshold == 0 and alert_threshold_value:
                product.alert_threshold = alert_threshold_value
                changed = True
            if product.price_sell <= 0 and price_sell_value > 0:
                product.price_sell = price_sell_value
                changed = True
            if changed:
                product.save()

    action = 'lưu' if created_product else 'chọn sản phẩm đã có'
    return JsonResponse({
        'ok': True,
        'product_id': product.id,
        'product_name': product.name,
        'sku': product.sku,
        'message': f"Đã {action} '{product.name}' · Mã: {product.sku}.",
    })


def product_create_view(request):
    next_target = request.GET.get('next') or request.POST.get('next') or ''
    product_id = request.GET.get('product_id') or request.POST.get('product_id')
    category_query = request.GET.get('category') or ''
    product_instance = for_user(Product, request.user).filter(pk=product_id).first() if product_id else None
    product_errors = []
    category_values = (
        [part.strip() for part in product_instance.category.split('/')[:4]]
        if product_instance and product_instance.category else ['', '', '', '']
    )
    if not product_instance and category_query:
        category_values = [part.strip() for part in category_query.split('/')[:4] if part.strip()]
        category_values += [''] * (4 - len(category_values))
    initial_purchase = {
        'quantity': '',
        'unit_price': '',
        'supplier_name': '',
        'date': timezone.now().date().isoformat(),
        'stock_origin': 'later' if product_instance else 'purchase',
        'notes': '',
        'payment_method': 'cash',
        'payment_due_date': '',
    }

    if request.method == 'POST':
        post_data = request.POST.copy()
        category_values = []
        for level in range(1, 5):
            selected = request.POST.get(f'category_level_{level}', '').strip()
            new_value = request.POST.get(f'category_level_{level}_new', '').strip()
            category_values.append(new_value or selected)
        submitted_category = ' / '.join([value for value in category_values if value])
        if product_instance and not submitted_category:
            submitted_category = product_instance.category
            category_values = (
                [part.strip() for part in submitted_category.split('/')[:4]]
                if submitted_category else ['', '', '', '']
            )
        post_data['category'] = submitted_category

        submitted_stock_origin = request.POST.get('stock_origin')
        has_submitted_stock = bool(
            request.POST.get('initial_stock_quantity', '').strip()
            or request.POST.get('initial_unit_cost', '').strip()
        )
        if submitted_stock_origin not in ('later', 'purchase'):
            submitted_stock_origin = 'purchase' if has_submitted_stock else 'later'
        if not product_instance and submitted_stock_origin == 'later':
            submitted_stock_origin = 'purchase'

        initial_purchase = {
            'quantity': request.POST.get('initial_stock_quantity', '').strip(),
            'unit_price': request.POST.get('initial_unit_cost', '').strip(),
            'supplier_name': request.POST.get('initial_supplier_name', '').strip(),
            'date': request.POST.get('initial_purchase_date') or timezone.now().date().isoformat(),
            'stock_origin': submitted_stock_origin,
            'notes': request.POST.get('initial_purchase_notes', '').strip(),
            'payment_method': request.POST.get('initial_payment_method', 'cash').strip(),
            'payment_due_date': request.POST.get('initial_payment_due_date', '').strip(),
        }

        form = ProductForm(post_data, instance=product_instance, user=request.user)

        purchase_quantity = 0
        purchase_unit_price = Decimal('0')
        purchase_date = timezone.now().date()
        if initial_purchase['stock_origin'] == 'later':
            purchase_quantity = 0
            purchase_unit_price = Decimal('0')
        else:
            try:
                purchase_quantity = int(initial_purchase['quantity'] or '0')
                if purchase_quantity < 0:
                    product_errors.append("Số tồn kho ban đầu không được âm.")
            except ValueError:
                product_errors.append("Số tồn kho ban đầu không hợp lệ.")

        if initial_purchase['stock_origin'] != 'later' and initial_purchase['unit_price']:
            try:
                purchase_unit_price = Decimal(str(initial_purchase['unit_price']).replace('.', '').replace(',', ''))
                if purchase_unit_price < 0:
                    product_errors.append("Giá vốn nhập không được âm.")
            except Exception:
                product_errors.append("Giá vốn nhập không hợp lệ.")

        if initial_purchase['stock_origin'] != 'later' and purchase_quantity <= 0:
            product_errors.append("Nếu nhập kho ngay, nhập số lượng lớn hơn 0 hoặc chọn chỉ tạo sản phẩm.")
        if initial_purchase['stock_origin'] != 'later' and purchase_unit_price <= 0:
            product_errors.append("Khi nhập kho sau onboarding, cần nhập giá vốn để tạo phiếu nhập hàng.")

        purchase_payment_method = 'cash'
        purchase_payment_due_date = None
        if initial_purchase['stock_origin'] != 'later':
            purchase_payment_method = initial_purchase['payment_method']
            if initial_purchase['payment_method'] == 'debt':
                if not initial_purchase['payment_due_date']:
                    product_errors.append("Khi chọn 'Nợ', cần nhập ngày nhắc nợ.")
                else:
                    try:
                        purchase_payment_due_date = datetime.strptime(initial_purchase['payment_due_date'], "%Y-%m-%d").date()
                        if purchase_payment_due_date < purchase_date:
                            product_errors.append("Ngày nhắc nợ không được trước ngày nhập hàng.")
                    except ValueError:
                        product_errors.append("Ngày nhắc nợ không hợp lệ.")

        try:
            purchase_date = datetime.strptime(initial_purchase['date'], "%Y-%m-%d").date()
        except ValueError:
            product_errors.append("Ngày nhập hàng ban đầu không hợp lệ.")

        if form.is_valid() and not product_errors:
            with transaction.atomic():
                product = form.save(commit=False)
                set_user(product, request.user)
                product.save()
                if product.category:
                    create_category_path(product.category, user=request.user)
                if purchase_quantity > 0:
                    Purchase.objects.create(
                        user=request.user,
                        product=product,
                        date=purchase_date,
                        supplier_name=initial_purchase['supplier_name'],
                        quantity=purchase_quantity,
                        unit_price=purchase_unit_price,
                        payment_method=purchase_payment_method,
                        payment_due_date=purchase_payment_due_date,
                        note=initial_purchase['notes'] or "Nhập hàng khi tạo sản phẩm",
                    )
            if next_target == 'expense_purchase':
                return redirect(f'/expenses/create/?mode=purchase&product_id={product.id}')
            product.refresh_from_db()
            if not product_instance:
                return redirect(f'/inventory/?created={product.id}')
            return redirect('/inventory/')
    else:
        form = ProductForm(instance=product_instance, user=request.user)

    category_level_options = product_category_levels(request.user)
    for level in category_level_options:
        selected = category_values[level['level'] - 1] if level['level'] - 1 < len(category_values) else ''
        level['selected'] = selected
        level['selected_is_option'] = selected in level['options']

    return render(request, 'core/product_form.html', {
        'form': form,
        'product_instance': product_instance,
        'category_levels': category_level_options,
        'category_values': category_values,
        'initial_purchase': initial_purchase,
        'next_target': next_target,
        'product_errors': product_errors,
    })

def purchase_delete_view(request, pk):
    purchase = get_object_or_404(for_user(Purchase, request.user), pk=pk)
    purchase.delete()
    return redirect('transaction_history')

def purchase_edit_view(request, pk):
    purchase = get_object_or_404(for_user(Purchase, request.user), pk=pk)
    if request.method == 'POST':
        form = PurchaseForm(request.POST, instance=purchase, user=request.user)
        if form.is_valid():
            purchase = form.save(commit=False)
            set_user(purchase, request.user)
            purchase.save()
            return redirect('transaction_history')
    return redirect('transaction_history')

def sale_delete_view(request, pk):
    sale = get_object_or_404(for_user(Sale, request.user), pk=pk)
    sale.delete()
    return redirect('transaction_history')


def sale_edit_view(request, pk):
    sale = get_object_or_404(for_user(Sale, request.user), pk=pk)
    if request.method == 'POST':
        form = SaleForm(request.POST, instance=sale, user=request.user)
        if form.is_valid():
            sale = form.save(commit=False)
            set_user(sale, request.user)
            sale.save()
            if form.cleaned_data.get('update_product_price'):
                sale.product.price_sell = sale.unit_price
                sale.product.save()
            return redirect('transaction_history')
    else:
        form = SaleForm(instance=sale, user=request.user)

    products = for_user(Product, request.user).filter(is_active=True).order_by('name')
    product_prices = {
        str(product.id): float(product.price_sell or 0)
        for product in products
    }
    product_options = [
        {
            'id': str(product.id),
            'name': product.name,
            'price': str(product.price_sell or 0),
        }
        for product in products
    ]
    context = transaction_page_context(request.user)
    context.update({
        'edit_mode': True,
        'form': form,
        'products': products,
        'product_prices': product_prices,
        'product_options': product_options,
        'sale_values': {
            'customer_name': sale.customer_name,
            'date': sale.date.isoformat(),
            'note': sale.note,
            'payment_method': sale.payment_method,
            'payment_due_date': sale.payment_due_date.isoformat() if sale.payment_due_date else '',
        },
        'sale_rows': [{
            'product': str(sale.product_id),
            'unit_price': str(sale.unit_price),
            'update_product_price': '0',
            'quantity': str(sale.quantity),
        }],
        'sale_errors': [],
        'payment_method_choices': Sale.PAYMENT_METHOD_CHOICES,
        'category_levels': product_category_levels(request.user),
        'category_tree': product_category_tree(request.user),
    })
    return render(request, 'core/sale_form.html', context)

def sale_create_view(request):
    products = for_user(Product, request.user).filter(is_active=True).order_by('name')
    today = timezone.now().date()
    sale_values = {
        'customer_name': '',
        'date': today.isoformat(),
        'note': '',
        'payment_method': Sale.PAYMENT_METHOD_CASH,
        'payment_due_date': '',
    }
    sale_rows = []
    sale_errors = []

    if request.method == 'POST':
        sale_values = {
            'customer_name': request.POST.get('customer_name', '').strip(),
            'date': request.POST.get('date') or today.isoformat(),
            'note': request.POST.get('note', '').strip(),
            'payment_method': request.POST.get('payment_method') or Sale.PAYMENT_METHOD_CASH,
            'payment_due_date': request.POST.get('payment_due_date', '').strip(),
        }
        product_ids = request.POST.getlist('order_product[]')
        new_product_names = request.POST.getlist('order_new_product_name[]')
        new_product_units = request.POST.getlist('order_new_product_unit[]')
        new_product_alerts = request.POST.getlist('order_new_product_alert[]')
        category_level_1 = request.POST.getlist('order_category_level_1[]')
        category_level_2 = request.POST.getlist('order_category_level_2[]')
        category_level_3 = request.POST.getlist('order_category_level_3[]')
        category_level_4 = request.POST.getlist('order_category_level_4[]')
        stock_quantities = request.POST.getlist('order_stock_quantity[]')
        stock_unit_costs = request.POST.getlist('order_stock_unit_cost[]')
        stock_origins = request.POST.getlist('order_stock_origin[]')
        stock_purchase_dates = request.POST.getlist('order_stock_purchase_date[]')
        stock_supplier_names = request.POST.getlist('order_stock_supplier_name[]')
        stock_notes = request.POST.getlist('order_stock_note[]')
        unit_prices = request.POST.getlist('order_unit_price[]')
        update_product_prices = request.POST.getlist('order_update_product_price[]')
        quantities = request.POST.getlist('order_quantity[]')
        max_rows = max(
            len(product_ids), len(new_product_names), len(new_product_units), len(new_product_alerts),
            len(category_level_1), len(category_level_2), len(category_level_3), len(category_level_4),
            len(stock_quantities), len(stock_unit_costs), len(stock_origins), len(stock_purchase_dates),
            len(stock_supplier_names), len(stock_notes),
            len(unit_prices), len(update_product_prices), len(quantities), 0
        )
        sale_records = []

        try:
            sale_date = datetime.strptime(sale_values['date'], "%Y-%m-%d").date()
        except ValueError:
            sale_date = today
            sale_errors.append("Ngày giao dịch không hợp lệ.")
        if sale_values['payment_method'] not in dict(Sale.PAYMENT_METHOD_CHOICES):
            sale_values['payment_method'] = Sale.PAYMENT_METHOD_CASH
        payment_due_date = None
        if sale_values['payment_method'] == Sale.PAYMENT_METHOD_DEBT:
            try:
                payment_due_date = datetime.strptime(sale_values['payment_due_date'], "%Y-%m-%d").date()
                if payment_due_date < today:
                    sale_errors.append("Ngày nhắc nợ không được sớm hơn hôm nay.")
            except ValueError:
                sale_errors.append("Chọn ngày nhắc nợ khi khách nợ/chưa thanh toán.")
        else:
            sale_values['payment_due_date'] = ''

        for index in range(max_rows):
            row = {
                'product': product_ids[index] if index < len(product_ids) else '',
                'new_product_name': new_product_names[index] if index < len(new_product_names) else '',
                'new_product_unit': new_product_units[index] if index < len(new_product_units) else '',
                'new_product_alert': new_product_alerts[index] if index < len(new_product_alerts) else '',
                'category_level_1': category_level_1[index] if index < len(category_level_1) else '',
                'category_level_2': category_level_2[index] if index < len(category_level_2) else '',
                'category_level_3': category_level_3[index] if index < len(category_level_3) else '',
                'category_level_4': category_level_4[index] if index < len(category_level_4) else '',
                'stock_quantity': stock_quantities[index] if index < len(stock_quantities) else '',
                'stock_unit_cost': stock_unit_costs[index] if index < len(stock_unit_costs) else '',
                'stock_origin': stock_origins[index] if index < len(stock_origins) else 'purchase',
                'stock_purchase_date': stock_purchase_dates[index] if index < len(stock_purchase_dates) else '',
                'stock_supplier_name': stock_supplier_names[index] if index < len(stock_supplier_names) else '',
                'stock_note': stock_notes[index] if index < len(stock_notes) else '',
                'unit_price': unit_prices[index] if index < len(unit_prices) else '',
                'update_product_price': update_product_prices[index] if index < len(update_product_prices) else '0',
                'quantity': quantities[index] if index < len(quantities) else '',
            }
            sale_rows.append(row)

            if not row['product'] and not row['new_product_name'] and not row['unit_price'] and not row['quantity']:
                continue

            row_label = f"Dòng {index + 1}"
            product = None
            if row['product'] == '__new__':
                if not row['new_product_name'].strip():
                    sale_errors.append(f"{row_label}: Nhập tên sản phẩm mới.")
                    continue
                if not row['category_level_1'].strip():
                    sale_errors.append(f"{row_label}: Sản phẩm mới cần có danh mục cấp 1.")
                    continue
                product = for_user(Product, request.user).filter(name__iexact=row['new_product_name'].strip()).first()
            else:
                try:
                    product = products.get(pk=row['product'])
                except Product.DoesNotExist:
                    sale_errors.append(f"{row_label}: Chọn sản phẩm hợp lệ hoặc thêm sản phẩm mới.")
                    continue

            try:
                unit_price = Decimal(str(row['unit_price'] or '0').replace('.', '').replace(',', ''))
                quantity = int(row['quantity'] or '0')
            except Exception:
                sale_errors.append(f"{row_label}: Đơn giá hoặc số lượng không hợp lệ.")
                continue

            if quantity <= 0:
                sale_errors.append(f"{row_label}: Số lượng phải lớn hơn 0.")
                continue
            if unit_price <= 0:
                sale_errors.append(f"{row_label}: Đơn giá bán là bắt buộc và phải lớn hơn 0.")
                continue

            stock_quantity = 0
            stock_unit_cost = Decimal('0')
            stock_origin = 'purchase'
            stock_purchase_date = sale_date
            if row['product'] == '__new__' and product is None:
                try:
                    stock_quantity = int(row['stock_quantity'] or '0')
                    stock_unit_cost = Decimal(str(row['stock_unit_cost'] or '0').replace('.', '').replace(',', ''))
                except Exception:
                    sale_errors.append(f"{row_label}: Nhập số lượng nhập kho và giá vốn hợp lệ cho sản phẩm mới.")
                    continue
                if stock_quantity <= 0:
                    sale_errors.append(f"{row_label}: Sản phẩm mới cần có số lượng nhập kho.")
                    continue
                if stock_unit_cost <= 0:
                    sale_errors.append(f"{row_label}: Giá vốn nhập là bắt buộc và phải lớn hơn 0.")
                    continue
                try:
                    stock_purchase_date = datetime.strptime(row['stock_purchase_date'] or sale_values['date'], "%Y-%m-%d").date()
                except ValueError:
                    sale_errors.append(f"{row_label}: Ngày nhập hàng không hợp lệ.")
                    continue

            available_stock = stock_quantity if product is None else product.stock_quantity
            if quantity > available_stock:
                product_name = product.name if product else row['new_product_name'].strip() or 'sản phẩm mới'
                sale_errors.append(
                    f"{row_label}: Số lượng bán của sản phẩm '{product_name}' vượt quá tồn kho hiện có ({available_stock}). "
                    f"Vui lòng kiểm tra tồn kho hoặc thêm tồn kho mới."
                )
                continue

            sale_records.append({
                'product': product,
                'new_product_name': row['new_product_name'].strip(),
                'new_product_unit': row['new_product_unit'].strip() or 'cái',
                'new_product_alert': row['new_product_alert'].strip(),
                'category_levels': [
                    row['category_level_1'].strip(),
                    row['category_level_2'].strip(),
                    row['category_level_3'].strip(),
                    row['category_level_4'].strip(),
                ],
                'stock_quantity': stock_quantity,
                'stock_unit_cost': stock_unit_cost,
                'stock_origin': stock_origin,
                'stock_purchase_date': stock_purchase_date,
                'stock_supplier_name': row['stock_supplier_name'].strip(),
                'stock_note': row['stock_note'].strip(),
                'unit_price': unit_price,
                'update_product_price': row['update_product_price'] == '1',
                'quantity': quantity,
            })

        if sale_records and not sale_errors:
            with transaction.atomic():
                for record in sale_records:
                    product = record['product']
                    if product is None:
                        try:
                            alert_threshold = int(record['new_product_alert'] or '10')
                        except ValueError:
                            alert_threshold = 10
                        product = Product.objects.create(
                            user=request.user,
                            name=record['new_product_name'],
                            category=' / '.join([level for level in record['category_levels'] if level]),
                            unit=record['new_product_unit'],
                            alert_threshold=max(alert_threshold, 0),
                            price_sell=record['unit_price'],
                        )
                        Purchase.objects.create(
                            user=request.user,
                            product=product,
                            date=record['stock_purchase_date'],
                            supplier_name=record['stock_supplier_name'],
                            quantity=record['stock_quantity'],
                            unit_price=record['stock_unit_cost'],
                            note=record['stock_note'] or 'Nhap hang khi tao san pham tu man hinh doanh thu.',
                        )
                    sale = Sale(
                        user=request.user,
                        product=product,
                        date=sale_date,
                        customer_name=sale_values['customer_name'],
                        quantity=record['quantity'],
                        unit_price=record['unit_price'],
                        payment_method=sale_values['payment_method'],
                        payment_due_date=payment_due_date,
                        note=sale_values['note'],
                    )
                    sale.save()
                    if record['update_product_price']:
                        sale.product.price_sell = sale.unit_price
                        sale.product.save()
            return redirect('transaction_history')

    if not sale_rows:
        product_id = request.GET.get('product_id')
        first_product = products.filter(pk=product_id).first() if product_id else products.first()
        sale_rows = [{
            'product': '',
            'new_product_name': '',
            'new_product_unit': '',
            'new_product_alert': '',
            'category_level_1': '',
            'category_level_2': '',
            'category_level_3': '',
            'category_level_4': '',
            'stock_quantity': '',
            'stock_unit_cost': '',
            'stock_origin': 'purchase',
            'stock_purchase_date': today.isoformat(),
            'stock_supplier_name': '',
            'stock_note': '',
            'unit_price':  '',
            'quantity': '1',
        }]

    product_prices = {
        str(product.id): float(product.price_sell or 0)
        for product in products
    }
    product_options = [
        {
            'id': str(product.id),
            'name': product.name,
            'price': str(product.price_sell or 0),
        }
        for product in products
    ]

    context = transaction_page_context(request.user)
    context.update({
        'products': products,
        'product_prices': product_prices,
        'product_options': product_options,
        'sale_values': sale_values,
        'sale_rows': sale_rows,
        'sale_errors': sale_errors,
        'payment_method_choices': Sale.PAYMENT_METHOD_CHOICES,
        'category_levels': product_category_levels(request.user),
        'category_tree': product_category_tree(request.user),
    })
    return render(request, 'core/sale_form.html', context)

def expense_delete_view(request, pk):
    expense = get_object_or_404(for_user(Expense, request.user), pk=pk)
    expense.delete()
    return redirect('transaction_history')


def expense_edit_view(request, pk):
    expense = get_object_or_404(for_user(Expense, request.user), pk=pk)
    products = for_user(Product, request.user).filter(is_active=True).order_by('name')
    if request.method == 'POST':
        form = ExpenseForm(request.POST, instance=expense)
        if form.is_valid():
            expense = form.save(commit=False)
            set_user(expense, request.user)
            expense.save()
            return redirect('transaction_history')
    else:
        form = ExpenseForm(instance=expense)
    context = transaction_page_context(request.user)
    context.update({
        'form': form,
        'edit_mode': True,
        'expense_mode': 'other',
        'products': products,
        'product_options': [
            {'id': str(product.id), 'name': product.name, 'price': str(product.price_buy_latest or 0)}
            for product in products
        ],
        'purchase_values': {
            'supplier_name': '',
            'date': timezone.now().date().isoformat(),
            'note': '',
            'payment_method': Purchase.PAYMENT_METHOD_CASH,
            'payment_due_date': '',
        },
        'purchase_rows': [],
        'other_expense_date': expense.date.isoformat(),
        'other_expense_values': {
            'date': expense.date.isoformat(),
            'payment_method': expense.payment_method,
            'payment_due_date': expense.payment_due_date.isoformat() if expense.payment_due_date else '',
        },
        'other_expense_rows': [],
        'payment_method_choices': Purchase.PAYMENT_METHOD_CHOICES,
        'expense_errors': [],
        'category_tree': product_category_tree(request.user),
    })
    return render(request, 'core/expense_form.html', context)

def expense_create_view(request):
    products = for_user(Product, request.user).filter(is_active=True).order_by('name')
    today = timezone.now().date()
    expense_mode = request.POST.get('expense_mode', 'other') if request.method == 'POST' else request.GET.get('mode', 'purchase')
    product_id = request.GET.get('product_id')
    purchase_values = {
        'supplier_name': '',
        'date': today.isoformat(),
        'note': '',
        'payment_method': Purchase.PAYMENT_METHOD_CASH,
        'payment_due_date': '',
    }
    purchase_rows = []
    other_expense_date = today.isoformat()
    other_expense_values = {
        'date': today.isoformat(),
        'payment_method': Expense.PAYMENT_METHOD_CASH,
        'payment_due_date': '',
    }
    other_expense_rows = []
    expense_errors = []

    if request.method == 'POST':
        if expense_mode == 'purchase':
            purchase_values = {
                'date': request.POST.get('purchase_date') or today.isoformat(),
                'supplier_name': request.POST.get('purchase_supplier_name', '').strip(),
                'note': request.POST.get('purchase_note', '').strip(),
                'payment_method': request.POST.get('purchase_payment_method') or Purchase.PAYMENT_METHOD_CASH,
                'payment_due_date': request.POST.get('purchase_payment_due_date', '').strip(),
            }
            product_ids = request.POST.getlist('purchase_product[]')
            new_product_names = request.POST.getlist('purchase_new_product_name[]')
            legacy_supplier_names = request.POST.getlist('purchase_supplier_name[]')
            if not purchase_values['supplier_name'] and legacy_supplier_names:
                purchase_values['supplier_name'] = legacy_supplier_names[0].strip()
            unit_prices = request.POST.getlist('purchase_unit_price[]')
            quantities = request.POST.getlist('purchase_quantity[]')
            max_rows = max(len(product_ids), len(new_product_names), len(unit_prices), len(quantities), 0)
            purchase_records = []
            created_product_ids = []

            try:
                purchase_date = datetime.strptime(purchase_values['date'], "%Y-%m-%d").date()
            except ValueError:
                purchase_date = today
                expense_errors.append("Ngày giao dịch không hợp lệ.")
            if purchase_values['payment_method'] not in dict(Purchase.PAYMENT_METHOD_CHOICES):
                purchase_values['payment_method'] = Purchase.PAYMENT_METHOD_CASH
            payment_due_date = None
            if purchase_values['payment_method'] == Purchase.PAYMENT_METHOD_DEBT:
                try:
                    payment_due_date = datetime.strptime(purchase_values['payment_due_date'], "%Y-%m-%d").date()
                    if payment_due_date < today:
                        expense_errors.append("Ngày cần thanh toán không được sớm hơn hôm nay.")
                except ValueError:
                    expense_errors.append("Chọn ngày cần thanh toán khi ghi nhận nợ/chưa thanh toán.")
            else:
                purchase_values['payment_due_date'] = ''

            for index in range(max_rows):
                row = {
                    'product': product_ids[index] if index < len(product_ids) else '',
                    'new_product_name': new_product_names[index] if index < len(new_product_names) else '',
                    'unit_price': unit_prices[index] if index < len(unit_prices) else '',
                    'quantity': quantities[index] if index < len(quantities) else '',
                }
                purchase_rows.append(row)

                if not row['product'] and not row['new_product_name'] and not row['unit_price'] and not row['quantity']:
                    continue

                row_label = f"Dòng {index + 1}"
                product = None
                new_product_name = row['new_product_name'].strip()
                if row['product'] == '__new__':
                    if not new_product_name:
                        expense_errors.append(f"{row_label}: Nhập tên sản phẩm mới.")
                        continue
                    product = for_user(Product, request.user).filter(name__iexact=new_product_name).first()
                else:
                    try:
                        product = products.get(pk=row['product'])
                    except Product.DoesNotExist:
                        expense_errors.append(f"{row_label}: Chọn sản phẩm hợp lệ hoặc chọn Sản phẩm mới.")
                        continue

                try:
                    unit_price = Decimal(str(row['unit_price'] or '0').replace('.', '').replace(',', ''))
                    quantity = int(row['quantity'] or '0')
                except Exception:
                    expense_errors.append(f"{row_label}: Đơn giá hoặc số lượng không hợp lệ.")
                    continue

                if quantity <= 0:
                    expense_errors.append(f"{row_label}: Số lượng nhập phải lớn hơn 0.")
                    continue
                if unit_price < 0:
                    expense_errors.append(f"{row_label}: Đơn giá nhập không hợp lệ.")
                    continue

                purchase_records.append({
                    'product': product,
                    'new_product_name': new_product_name,
                    'supplier_name': purchase_values['supplier_name'],
                    'quantity': quantity,
                    'unit_price': unit_price,
                })

            if purchase_records and not expense_errors:
                with transaction.atomic():
                    for record in purchase_records:
                        product = record['product']
                        if product is None:
                            product = Product.objects.create(
                                user=request.user,
                                name=record['new_product_name'],
                                category='',
                                unit='cái',
                                alert_threshold=10,
                                price_sell=0,
                            )
                            created_product_ids.append(product.id)

                        Purchase.objects.create(
                            user=request.user,
                            product=product,
                            date=purchase_date,
                            supplier_name=record['supplier_name'],
                            quantity=record['quantity'],
                            unit_price=record['unit_price'],
                            payment_method=purchase_values['payment_method'],
                            payment_due_date=payment_due_date,
                            note=purchase_values['note'],
                        )
                return redirect('transaction_history')

            form = ExpenseForm(initial={'date': today})
        else:
            other_expense_date = request.POST.get('expense_date') or today.isoformat()
            other_expense_values = {
                'date': other_expense_date,
                'payment_method': request.POST.get('expense_payment_method') or Expense.PAYMENT_METHOD_CASH,
                'payment_due_date': request.POST.get('expense_payment_due_date', '').strip(),
            }
            expense_types = request.POST.getlist('expense_type[]')
            amounts = request.POST.getlist('expense_amount[]')
            estimated_lifetimes = request.POST.getlist('expense_estimated_lifetime_months[]')
            notes = request.POST.getlist('expense_note[]')
            equipment_memos = request.POST.getlist('expense_equipment_memo[]')
            max_rows = max(len(expense_types), len(amounts), len(estimated_lifetimes), len(notes), len(equipment_memos), 0)
            expenses_to_create = []

            try:
                expense_date = datetime.strptime(other_expense_date, "%Y-%m-%d").date()
            except ValueError:
                expense_date = today
                expense_errors.append("Ngày giao dịch không hợp lệ.")
            if other_expense_values['payment_method'] not in dict(Expense.PAYMENT_METHOD_CHOICES):
                other_expense_values['payment_method'] = Expense.PAYMENT_METHOD_CASH
            expense_payment_due_date = None
            if other_expense_values['payment_method'] == Expense.PAYMENT_METHOD_DEBT:
                try:
                    expense_payment_due_date = datetime.strptime(other_expense_values['payment_due_date'], "%Y-%m-%d").date()
                    if expense_payment_due_date < today:
                        expense_errors.append("Ngày cần thanh toán không được sớm hơn hôm nay.")
                except ValueError:
                    expense_errors.append("Chọn ngày cần thanh toán khi chi phí chưa thanh toán.")
            else:
                other_expense_values['payment_due_date'] = ''

            for index in range(max_rows):
                row = {
                    'expense_type': expense_types[index] if index < len(expense_types) else '',
                    'amount': amounts[index] if index < len(amounts) else '',
                    'estimated_lifetime_months': estimated_lifetimes[index] if index < len(estimated_lifetimes) else '',
                    'note': notes[index] if index < len(notes) else '',
                    'equipment_memo': equipment_memos[index] if index < len(equipment_memos) else '',
                }
                other_expense_rows.append(row)

                if not any(row.values()):
                    continue

                row_label = f"Dòng {index + 1}"
                try:
                    amount = Decimal(str(row['amount'] or '0').replace('.', '').replace(',', ''))
                except Exception:
                    expense_errors.append(f"{row_label}: Số tiền không hợp lệ.")
                    continue
                lifetime_months = None
                if row['estimated_lifetime_months']:
                    try:
                        lifetime_months = int(row['estimated_lifetime_months'])
                    except ValueError:
                        lifetime_months = 0
                    if lifetime_months <= 0:
                        expense_errors.append(f"{row_label}: Thời gian sử dụng phải lớn hơn 0 tháng.")
                        continue
                if row['expense_type'] == Expense.EXPENSE_TYPE_EQUIPMENT:
                    if not row['note'].strip():
                        expense_errors.append(f"{row_label}: Nhập tên thiết bị.")
                        continue
                    if not lifetime_months:
                        expense_errors.append(f"{row_label}: Nhập vòng đời của thiết bị theo số tháng.")
                        continue
                    expense_note = row['note'].strip()
                    if row['equipment_memo'].strip():
                        expense_note = f"{expense_note}\n{row['equipment_memo'].strip()}"
                else:
                    expense_note = row['note']

                expense = Expense(
                    user=request.user,
                    date=expense_date,
                    expense_type=row['expense_type'],
                    amount=amount,
                    estimated_lifetime_months=lifetime_months,
                    payment_method=other_expense_values['payment_method'],
                    payment_due_date=expense_payment_due_date,
                    note=expense_note,
                )
                try:
                    expense.full_clean()
                    expenses_to_create.append(expense)
                except ValidationError as exc:
                    expense_errors.append(f"{row_label}: {exc}")

            if expenses_to_create and not expense_errors:
                with transaction.atomic():
                    for expense in expenses_to_create:
                        expense.save()
                return redirect('transaction_history')

            form = ExpenseForm(initial={'date': other_expense_date})
    else:
        form = ExpenseForm(initial={'date': timezone.now().date()})

    if not purchase_rows:
        purchase_rows = [{
            'product': product_id or '',
            'new_product_name': '',
            'unit_price': '',
            'quantity': '1' if product_id else '',
        }]
    if not other_expense_rows:
        other_expense_rows = [{
            'expense_type': Expense.EXPENSE_TYPE_CHOICES[0][0],
            'amount': '',
            'estimated_lifetime_months': '',
            'note': '',
            'equipment_memo': '',
        }]

    context = transaction_page_context(request.user)
    context.update({
        'form': form,
        'expense_mode': expense_mode,
        'products': products,
        'product_options': [
            {'id': str(product.id), 'name': product.name, 'price': str(product.price_buy_latest or 0)}
            for product in products
        ],
        'purchase_values': purchase_values,
        'purchase_rows': purchase_rows,
        'other_expense_date': other_expense_date,
        'other_expense_values': other_expense_values,
        'other_expense_rows': other_expense_rows,
        'expense_type_choices': Expense.EXPENSE_TYPE_CHOICES,
        'payment_method_choices': Purchase.PAYMENT_METHOD_CHOICES,
        'expense_errors': expense_errors,
        'category_tree': product_category_tree(request.user),
    })
    return render(request, 'core/expense_form.html', context)


def transaction_create_view(request):
    return sale_create_view(request)


@require_POST
def mark_transaction_paid_view(request, kind, pk):
    model_map = {
        'sale': Sale,
        'purchase': Purchase,
        'expense': Expense,
    }
    model = model_map.get(kind)
    if not model:
        return JsonResponse({'ok': False, 'error': 'Loại giao dịch không hợp lệ.'}, status=400)
    record = get_object_or_404(for_user(model, request.user), pk=pk)
    payment_method = request.POST.get('payment_method') or model.PAYMENT_METHOD_CASH
    if payment_method not in dict(model.PAYMENT_METHOD_CHOICES):
        payment_method = model.PAYMENT_METHOD_CASH
    payment_date_raw = request.POST.get('payment_date') or timezone.now().date().isoformat()
    try:
        payment_date = datetime.strptime(payment_date_raw, "%Y-%m-%d").date()
    except ValueError:
        payment_date = timezone.now().date()
    note = request.POST.get('note', '').strip()
    record.payment_method = payment_method
    record.payment_due_date = None
    record.payment_date = payment_date
    if note:
        prefix = f"Đã thanh toán {payment_date.strftime('%d/%m/%Y')}"
        record.note = f"{record.note}\n{prefix}: {note}".strip() if record.note else f"{prefix}: {note}"
    record.save()
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'ok': True,
            'payment_method': record.payment_method,
            'payment_date': record.payment_date.isoformat() if record.payment_date else '',
            'payment_label': record.get_payment_method_display(),
        })
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or '/transactions/history/'
    return redirect(next_url)


@require_POST
def extend_transaction_due_view(request, kind, pk):
    model_map = {
        'sale': Sale,
        'purchase': Purchase,
        'expense': Expense,
    }
    model = model_map.get(kind)
    if not model:
        return JsonResponse({'ok': False, 'error': 'Loại giao dịch không hợp lệ.'}, status=400)
    record = get_object_or_404(for_user(model, request.user), pk=pk)
    due_raw = request.POST.get('new_due_date', '').strip()
    try:
        new_due_date = datetime.strptime(due_raw, "%Y-%m-%d").date()
    except ValueError:
        return JsonResponse({'ok': False, 'error': 'Chọn hạn thanh toán mới.'}, status=400)
    if new_due_date < timezone.now().date():
        return JsonResponse({'ok': False, 'error': 'Hạn mới không được sớm hơn hôm nay.'}, status=400)
    note = request.POST.get('note', '').strip()
    record.payment_method = model.PAYMENT_METHOD_DEBT
    record.payment_due_date = new_due_date
    record.payment_date = None
    if note:
        prefix = f"Đổi hạn thanh toán sang {new_due_date.strftime('%d/%m/%Y')}"
        record.note = f"{record.note}\n{prefix}: {note}".strip() if record.note else f"{prefix}: {note}"
    record.save()
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        status = transaction_payment_status(record.payment_method, record.payment_due_date)
        return JsonResponse({
            'ok': True,
            'due_date': record.payment_due_date.isoformat(),
            'due_date_display': record.payment_due_date.strftime('%d/%m/%Y'),
            'status': status,
        })
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or '/transactions/history/'
    return redirect(next_url)


def bulk_transaction_create_view(request):
    products = for_user(Product, request.user).filter(is_active=True).order_by('name')
    expense_type_choices = Expense.EXPENSE_TYPE_CHOICES
    rows = []
    row_errors = {}
    today = timezone.now().date()

    if request.method == 'POST':
        types = request.POST.getlist('transaction_type[]')
        dates = request.POST.getlist('date[]')
        product_ids = request.POST.getlist('product[]')
        expense_types = request.POST.getlist('expense_type[]')
        estimated_lifetimes = request.POST.getlist('estimated_lifetime_months[]')
        partners = request.POST.getlist('partner[]')
        unit_prices = request.POST.getlist('unit_price[]')
        quantities = request.POST.getlist('quantity[]')
        payment_methods = request.POST.getlist('payment_method[]')
        payment_due_dates = request.POST.getlist('payment_due_date[]')
        notes = request.POST.getlist('note[]')
        max_rows = max(len(types), len(dates), len(product_ids), len(expense_types), len(estimated_lifetimes), len(partners), len(unit_prices), len(quantities), len(payment_methods), len(payment_due_dates), len(notes), 0)
        records = []

        def mark_row_errors(index, row, errors):
            row_errors[index] = [f"Dòng {index + 1}: {error}" for error in errors]
            row['errors'] = row_errors[index]

        for index in range(max_rows):
            row = {
                'transaction_type': types[index] if index < len(types) else 'income',
                'date': dates[index] if index < len(dates) else '',
                'product': product_ids[index] if index < len(product_ids) else '',
                'expense_type': expense_types[index] if index < len(expense_types) else '',
                'estimated_lifetime_months': estimated_lifetimes[index] if index < len(estimated_lifetimes) else '',
                'partner': partners[index] if index < len(partners) else '',
                'unit_price': unit_prices[index] if index < len(unit_prices) else '',
                'quantity': quantities[index] if index < len(quantities) else '',
                'payment_method': payment_methods[index] if index < len(payment_methods) else Sale.PAYMENT_METHOD_CASH,
                'payment_due_date': payment_due_dates[index] if index < len(payment_due_dates) else '',
                'note': notes[index] if index < len(notes) else '',
            }
            rows.append(row)

            normalized_price = str(row['unit_price'] or '').replace('.', '').replace(',', '').strip()
            normalized_quantity = str(row['quantity'] or '').strip()
            extra_products_for_blank = request.POST.getlist(f'extra_product_{index}[]')
            extra_prices_for_blank = request.POST.getlist(f'extra_unit_price_{index}[]')
            extra_quantities_for_blank = request.POST.getlist(f'extra_quantity_{index}[]')
            is_blank = not any([
                row['product'],
                row['expense_type'],
                row['estimated_lifetime_months'],
                row['partner'].strip(),
                row['note'].strip(),
                normalized_price not in ('', '0'),
                normalized_quantity not in ('', '1'),
                any(extra_products_for_blank),
                any(value for value in extra_prices_for_blank if str(value).strip()),
                any(value for value in extra_quantities_for_blank if str(value).strip() and str(value).strip() != '1'),
            ])
            if is_blank:
                continue

            errors = []
            try:
                row_date = datetime.strptime(row['date'], "%Y-%m-%d").date() if row['date'] else timezone.now().date()
            except ValueError:
                row_date = timezone.now().date()
                errors.append("Ngày không hợp lệ.")

            try:
                unit_price = Decimal(row['unit_price'] or '0')
            except Exception:
                unit_price = Decimal('0')
                errors.append("Đơn giá/số tiền không hợp lệ.")

            try:
                quantity = int(row['quantity'] or '1')
            except ValueError:
                quantity = 1
                errors.append("Số lượng không hợp lệ.")

            if unit_price < 0:
                errors.append("Giá trị không được âm.")
            if quantity <= 0:
                errors.append("Số lượng phải lớn hơn 0.")
            if unit_price <= 0:
                errors.append("Giá trị phải lớn hơn 0.")
            payment_method_choices = dict(Sale.PAYMENT_METHOD_CHOICES)
            if row['payment_method'] not in payment_method_choices:
                row['payment_method'] = Sale.PAYMENT_METHOD_CASH
            payment_due_date = None
            if row['transaction_type'] in ('income', 'purchase', 'expense') and row['payment_method'] == Sale.PAYMENT_METHOD_DEBT:
                try:
                    payment_due_date = datetime.strptime(row['payment_due_date'], "%Y-%m-%d").date()
                    if payment_due_date < today:
                        errors.append("Ngày cần thanh toán không được sớm hơn hôm nay.")
                except ValueError:
                    errors.append("Chọn ngày cần thanh toán/nhắc nợ khi chọn nợ.")

            if errors:
                mark_row_errors(index, row, errors)
                continue

            if row['transaction_type'] == 'income':
                extra_products = request.POST.getlist(f'extra_product_{index}[]')
                extra_prices = request.POST.getlist(f'extra_unit_price_{index}[]')
                extra_quantities = request.POST.getlist(f'extra_quantity_{index}[]')
                has_extra_product = any(value for value in extra_products)
                if not row['product'] and not has_extra_product:
                    errors.append("Chọn sản phẩm cho doanh thu.")
                if row['product']:
                    try:
                        product = products.get(pk=row['product'])
                        record = Sale(
                            user=request.user,
                            product=product,
                            date=row_date,
                            customer_name=row['partner'],
                            quantity=quantity,
                            unit_price=unit_price,
                            payment_method=row['payment_method'],
                            payment_due_date=payment_due_date,
                            note=row['note'],
                        )
                        record.full_clean()
                        records.append(record)
                    except (Product.DoesNotExist, ValidationError) as exc:
                        errors.append(str(exc))
                for item_index, extra_product_id in enumerate(extra_products):
                    extra_product_id = str(extra_product_id or '').strip()
                    extra_price_raw = extra_prices[item_index] if item_index < len(extra_prices) else ''
                    extra_quantity_raw = extra_quantities[item_index] if item_index < len(extra_quantities) else ''
                    if not extra_product_id and not extra_price_raw and not extra_quantity_raw:
                        continue
                    try:
                        extra_unit_price = Decimal(str(extra_price_raw or '0').replace('.', '').replace(',', ''))
                        extra_quantity = int(extra_quantity_raw or '1')
                    except Exception:
                        errors.append(f"Sản phẩm thêm {item_index + 1}: giá hoặc số lượng không hợp lệ.")
                        continue
                    if not extra_product_id:
                        errors.append(f"Sản phẩm thêm {item_index + 1}: chọn sản phẩm.")
                        continue
                    if extra_unit_price <= 0:
                        errors.append(f"Sản phẩm thêm {item_index + 1}: giá bán phải lớn hơn 0.")
                        continue
                    if extra_quantity <= 0:
                        errors.append(f"Sản phẩm thêm {item_index + 1}: số lượng phải lớn hơn 0.")
                        continue
                    try:
                        product = products.get(pk=extra_product_id)
                        record = Sale(
                            user=request.user,
                            product=product,
                            date=row_date,
                            customer_name=row['partner'],
                            quantity=extra_quantity,
                            unit_price=extra_unit_price,
                            payment_method=row['payment_method'],
                            payment_due_date=payment_due_date,
                            note=row['note'],
                        )
                        record.full_clean()
                        records.append(record)
                    except (Product.DoesNotExist, ValidationError) as exc:
                        errors.append(str(exc))
            elif row['transaction_type'] == 'purchase':
                extra_products = request.POST.getlist(f'extra_product_{index}[]')
                extra_prices = request.POST.getlist(f'extra_unit_price_{index}[]')
                extra_quantities = request.POST.getlist(f'extra_quantity_{index}[]')
                has_extra_product = any(value for value in extra_products)
                if not row['product'] and not has_extra_product:
                    errors.append("Chọn sản phẩm cho nhập hàng.")
                if row['product']:
                    try:
                        product = products.get(pk=row['product'])
                        record = Purchase(
                            user=request.user,
                            product=product,
                            date=row_date,
                            supplier_name=row['partner'],
                            quantity=quantity,
                            unit_price=unit_price,
                            payment_method=row['payment_method'],
                            payment_due_date=payment_due_date,
                            note=row['note'],
                        )
                        record.full_clean()
                        records.append(record)
                    except (Product.DoesNotExist, ValidationError) as exc:
                        errors.append(str(exc))
                for item_index, extra_product_id in enumerate(extra_products):
                    extra_product_id = str(extra_product_id or '').strip()
                    extra_price_raw = extra_prices[item_index] if item_index < len(extra_prices) else ''
                    extra_quantity_raw = extra_quantities[item_index] if item_index < len(extra_quantities) else ''
                    if not extra_product_id and not extra_price_raw and not extra_quantity_raw:
                        continue
                    try:
                        extra_unit_price = Decimal(str(extra_price_raw or '0').replace('.', '').replace(',', ''))
                        extra_quantity = int(extra_quantity_raw or '1')
                    except Exception:
                        errors.append(f"Sản phẩm thêm {item_index + 1}: giá hoặc số lượng không hợp lệ.")
                        continue
                    if not extra_product_id:
                        errors.append(f"Sản phẩm thêm {item_index + 1}: chọn sản phẩm.")
                        continue
                    if extra_unit_price <= 0:
                        errors.append(f"Sản phẩm thêm {item_index + 1}: giá nhập phải lớn hơn 0.")
                        continue
                    if extra_quantity <= 0:
                        errors.append(f"Sản phẩm thêm {item_index + 1}: số lượng phải lớn hơn 0.")
                        continue
                    try:
                        product = products.get(pk=extra_product_id)
                        record = Purchase(
                            user=request.user,
                            product=product,
                            date=row_date,
                            supplier_name=row['partner'],
                            quantity=extra_quantity,
                            unit_price=extra_unit_price,
                            payment_method=row['payment_method'],
                            payment_due_date=payment_due_date,
                            note=row['note'],
                        )
                        record.full_clean()
                        records.append(record)
                    except (Product.DoesNotExist, ValidationError) as exc:
                        errors.append(str(exc))
            else:
                if not row['expense_type']:
                    errors.append("Chọn nhóm chi phí.")
                else:
                    lifetime_months = None
                    if row['expense_type'] == Expense.EXPENSE_TYPE_EQUIPMENT:
                        try:
                            lifetime_months = int(row['estimated_lifetime_months'] or '0')
                        except ValueError:
                            lifetime_months = 0
                        if not row['note'].strip():
                            errors.append("Nhập tên thiết bị.")
                        if lifetime_months <= 0:
                            errors.append("Nhập vòng đời của thiết bị theo số tháng.")
                    record = Expense(
                        user=request.user,
                        date=row_date,
                        expense_type=row['expense_type'],
                        amount=unit_price * quantity,
                        estimated_lifetime_months=lifetime_months,
                        payment_method=row['payment_method'],
                        payment_due_date=payment_due_date,
                        note=row['note'] or row['partner'],
                    )
                    try:
                        record.full_clean()
                        records.append(record)
                    except ValidationError as exc:
                        errors.append(str(exc))

            if errors:
                mark_row_errors(index, row, errors)

        if records and not row_errors:
            saved_count = len(records)
            with transaction.atomic():
                for record in records:
                    record.save()
            return redirect(f'/transactions/bulk-create/?saved={saved_count}')

    if not rows:
        today = today.isoformat()
        rows = [
            {'transaction_type': 'income', 'date': today, 'product': '', 'expense_type': '', 'estimated_lifetime_months': '', 'partner': '', 'unit_price': '', 'quantity': '1', 'payment_method': Sale.PAYMENT_METHOD_CASH, 'payment_due_date': '', 'note': ''}
            for _ in range(8)
        ]

    context = transaction_page_context(request.user)
    context.update({
        'products': products,
        'expense_type_choices': expense_type_choices,
        'payment_method_choices': Sale.PAYMENT_METHOD_CHOICES,
        'bulk_rows': rows,
        'row_errors': row_errors,
        'saved_count': request.GET.get('saved', ''),
    })
    return render(request, 'core/bulk_transaction_form.html', context)


def transaction_history_view(request):
    import json
    tx_type = request.GET.get('type', 'all')
    query = request.GET.get('q', '').strip()
    query_normalized = query.lower()
    date_from_raw = request.GET.get('date_from', '').strip()
    date_to_raw = request.GET.get('date_to', '').strip()
    date_filter_mode = request.GET.get('date_filter_mode', '').strip()
    date_value_raw = request.GET.get('date_value', '').strip()
    date_start_raw = request.GET.get('date_start', '').strip()
    date_end_raw = request.GET.get('date_end', '').strip()
    show_product_codes = request.GET.get('show_codes') == '1'
    type_filters = [value for value in request.GET.getlist('type_filter') if value in ('income', 'purchase', 'expense')]
    if tx_type in ('income', 'purchase', 'expense') and not type_filters:
        type_filters = [tx_type]
    if set(type_filters) == {'income', 'purchase', 'expense'}:
        type_filters = []
        tx_type = 'all'
    elif tx_type == 'all' and len(type_filters) == 1:
        tx_type = type_filters[0]
    description_filters = [value for value in request.GET.getlist('description_filter') if value]
    partner_filters = [value for value in request.GET.getlist('partner_filter') if value]
    payment_filters = [value for value in request.GET.getlist('payment_filter') if value]
    quantity_filter_mode = request.GET.get('quantity_filter_mode', '').strip()
    quantity_value_raw = request.GET.get('quantity_value', '').strip()
    quantity_min_raw = request.GET.get('quantity_min', '').strip()
    quantity_max_raw = request.GET.get('quantity_max', '').strip()
    amount_filter_mode = request.GET.get('amount_filter_mode', '').strip()
    amount_value_raw = request.GET.get('amount_value', '').strip()
    amount_min_raw = request.GET.get('amount_min', '').strip()
    amount_max_raw = request.GET.get('amount_max', '').strip()
    sort_field = request.GET.get('sort', '').strip()
    sort_dir = request.GET.get('dir', '').strip()
    transactions = []
    today = timezone.now().date()
    user_sales = for_user(Sale, request.user)
    user_purchases = for_user(Purchase, request.user)
    user_expenses = for_user(Expense, request.user)

    all_dates = []
    all_dates.extend(user_sales.values_list('date', flat=True))
    all_dates.extend(user_purchases.values_list('date', flat=True))
    all_dates.extend(user_expenses.values_list('date', flat=True))
    earliest_date = min(all_dates) if all_dates else timezone.now().date()
    if not date_from_raw:
        date_from_raw = earliest_date.isoformat()
    if not date_to_raw:
        date_to_raw = timezone.now().date().isoformat()
    if date_filter_mode == 'range':
        if not date_start_raw:
            date_start_raw = earliest_date.isoformat()
        if not date_end_raw:
            date_end_raw = timezone.now().date().isoformat()
    elif date_filter_mode == 'before' and not date_value_raw:
        date_value_raw = timezone.now().date().isoformat()
    elif date_filter_mode == 'after' and not date_value_raw:
        date_value_raw = earliest_date.isoformat()
    if date_filter_mode == 'before' and date_value_raw:
        date_from_raw = earliest_date.isoformat()
        date_to_raw = date_value_raw
    elif date_filter_mode == 'after' and date_value_raw:
        date_from_raw = date_value_raw
        date_to_raw = timezone.now().date().isoformat()
    elif date_filter_mode == 'range':
        if date_start_raw:
            date_from_raw = date_start_raw
        if date_end_raw:
            date_to_raw = date_end_raw

    def parse_filter_date(value):
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return None

    date_from = parse_filter_date(date_from_raw)
    date_to = parse_filter_date(date_to_raw)
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from
        date_from_raw, date_to_raw = date_to_raw, date_from_raw

    def parse_amount(value):
        if not value:
            return None
        cleaned = str(value).replace('.', '').replace(',', '').strip()
        try:
            return Decimal(cleaned)
        except Exception:
            return None

    amount_value = parse_amount(amount_value_raw)
    amount_min = parse_amount(amount_min_raw)
    amount_max = parse_amount(amount_max_raw)
    quantity_value = parse_amount(quantity_value_raw)
    quantity_min = parse_amount(quantity_min_raw)
    quantity_max = parse_amount(quantity_max_raw)
    if amount_min is not None and amount_max is not None and amount_min > amount_max:
        amount_min, amount_max = amount_max, amount_min
        amount_min_raw, amount_max_raw = amount_max_raw, amount_min_raw
    if quantity_min is not None and quantity_max is not None and quantity_min > quantity_max:
        quantity_min, quantity_max = quantity_max, quantity_min
        quantity_min_raw, quantity_max_raw = quantity_max_raw, quantity_min_raw

    if tx_type in ('all', 'income'):
        for sale in user_sales.select_related('product'):
            transactions.append({
                'id': sale.id,
                'kind': 'income',
                'payment_kind': 'sale',
                'raw_id': f'tx-raw-income-{sale.id}',
                'label': 'Doanh thu',
                'date': sale.date,
                'saved_at': sale.updated_at or sale.created_at,
                'partner': sale.customer_name or 'Khách lẻ',
                'description': sale.product.name,
                'code': sale.product.sku,
                'quantity': sale.quantity,
                'amount': sale.total_amount,
                'payment_status': transaction_payment_status(sale.payment_method, sale.payment_due_date, today),
                'edit_url': f'/transactions/sales/{sale.id}/edit/',
                'delete_url': f'/transactions/sales/{sale.id}/delete/',
                'raw': json.dumps({
                    'product_id': sale.product.id,
                    'date': sale.date.isoformat(),
                    'customer_name': sale.customer_name,
                    'quantity': sale.quantity,
                    'unit_price': float(sale.unit_price),
                    'payment_method': sale.payment_method,
                    'payment_due_date': sale.payment_due_date.isoformat() if sale.payment_due_date else '',
                    'note': sale.note,
                })
            })

    if tx_type in ('all', 'purchase'):
        for purchase in user_purchases.select_related('product'):
            transactions.append({
                'id': purchase.id,
                'kind': 'purchase',
                'payment_kind': 'purchase',
                'raw_id': f'tx-raw-purchase-{purchase.id}',
                'label': 'Nhập hàng',
                'date': purchase.date,
                'saved_at': purchase.updated_at or purchase.created_at,
                'partner': purchase.supplier_name or 'Nhà cung cấp',
                'description': purchase.product.name,
                'code': purchase.product.sku,
                'quantity': purchase.quantity,
                'amount': -purchase.total_amount,
                'payment_status': transaction_payment_status(purchase.payment_method, purchase.payment_due_date, today),
                'edit_url': f'/transactions/purchases/{purchase.id}/edit/',
                'delete_url': f'/transactions/purchases/{purchase.id}/delete/',
                'raw': json.dumps({
                    'product_id': purchase.product.id,
                    'date': purchase.date.isoformat(),
                    'supplier_name': purchase.supplier_name,
                    'quantity': purchase.quantity,
                    'unit_price': float(purchase.unit_price),
                    'payment_method': purchase.payment_method,
                    'payment_due_date': purchase.payment_due_date.isoformat() if purchase.payment_due_date else '',
                    'note': purchase.note,
                })
            })

    if tx_type in ('all', 'expense'):
        for expense in user_expenses:
            transactions.append({
                'id': expense.id,
                'kind': 'expense',
                'payment_kind': 'expense',
                'raw_id': f'tx-raw-expense-{expense.id}',
                'label': 'Chi phí',
                'date': expense.date,
                'saved_at': expense.updated_at or expense.created_at,
                'partner': '-',
                'description': expense.get_expense_type_display(),
                'code': f'CP-{expense.id:03d}',
                'quantity': 1,
                'amount': -expense.amount,
                'payment_status': transaction_payment_status(expense.payment_method, expense.payment_due_date, today),
                'edit_url': f'/transactions/expenses/{expense.id}/edit/',
                'delete_url': f'/transactions/expenses/{expense.id}/delete/',
                'raw': json.dumps({
                    'expense_type': expense.expense_type,
                    'date': expense.date.isoformat(),
                    'amount': float(expense.amount),
                    'estimated_lifetime_months': expense.estimated_lifetime_months or '',
                    'payment_method': expense.payment_method,
                    'payment_due_date': expense.payment_due_date.isoformat() if expense.payment_due_date else '',
                    'note': expense.note,
                })
            })

    if query:
        transactions = [
            item for item in transactions
            if query_normalized in item['description'].lower()
            or query_normalized in item['partner'].lower()
            or query_normalized in item['label'].lower()
            or query_normalized in item['code'].lower()
            or query_normalized in item['payment_status']['label'].lower()
            or query_normalized in item['payment_status']['key'].lower()
            or query_normalized in str(abs(item['amount']))
            or query_normalized in f"{int(abs(item['amount'])):,}".replace(',', '.')
            or query_normalized in f"{int(abs(item['amount'])):,}".replace(',', '')
        ]

    if date_from:
        transactions = [item for item in transactions if item['date'] >= date_from]
    if date_to:
        transactions = [item for item in transactions if item['date'] <= date_to]

    type_options = [
        {'value': 'income', 'label': 'Doanh thu'},
        {'value': 'purchase', 'label': 'Nhập hàng'},
        {'value': 'expense', 'label': 'Chi phí khác'},
    ]
    if type_filters:
        transactions = [item for item in transactions if item['kind'] in type_filters]

    description_options = sorted({item['description'] for item in transactions})
    partner_options = sorted({item['partner'] for item in transactions})
    payment_options = sorted(
        {item['payment_status']['key']: item['payment_status']['label'] for item in transactions}.items(),
        key=lambda item: item[1]
    )
    if description_filters:
        transactions = [item for item in transactions if item['description'] in description_filters]
    if partner_filters:
        transactions = [item for item in transactions if item['partner'] in partner_filters]
    if payment_filters:
        transactions = [item for item in transactions if item['payment_status']['key'] in payment_filters]

    def number_matches(value, mode, single, minimum, maximum):
        if mode == 'eq' and single is not None:
            return value == single
        if mode == 'gt' and single is not None:
            return value > single
        if mode == 'lt' and single is not None:
            return value < single
        if mode == 'range':
            if minimum is not None and value < minimum:
                return False
            if maximum is not None and value > maximum:
                return False
            return minimum is not None or maximum is not None
        return True

    if quantity_filter_mode:
        transactions = [
            item for item in transactions
            if number_matches(Decimal(str(item['quantity'])), quantity_filter_mode, quantity_value, quantity_min, quantity_max)
        ]
    if amount_filter_mode == 'gt' and amount_value is not None:
        transactions = [item for item in transactions if abs(item['amount']) > amount_value]
    elif amount_filter_mode == 'lt' and amount_value is not None:
        transactions = [item for item in transactions if abs(item['amount']) < amount_value]
    elif amount_filter_mode == 'eq' and amount_value is not None:
        transactions = [item for item in transactions if abs(item['amount']) == amount_value]
    elif amount_filter_mode == 'range':
        if amount_min is not None:
            transactions = [item for item in transactions if abs(item['amount']) >= amount_min]
        if amount_max is not None:
            transactions = [item for item in transactions if abs(item['amount']) <= amount_max]

    sort_key_map = {
        'type': lambda item: item['label'].lower(),
        'date': lambda item: item['date'],
        'description': lambda item: item['description'].lower(),
        'partner': lambda item: item['partner'].lower(),
        'quantity': lambda item: item['quantity'],
        'amount': lambda item: item['amount'],
        'payment': lambda item: item['payment_status']['label'].lower(),
    }
    if sort_field in sort_key_map and sort_dir in ('asc', 'desc'):
        transactions.sort(key=sort_key_map[sort_field], reverse=(sort_dir == 'desc'))
    else:
        sort_field = ''
        sort_dir = ''
        transactions.sort(
            key=lambda item: (item.get('saved_at') or datetime.min.replace(tzinfo=timezone.get_current_timezone()), item['date'], item['id']),
            reverse=True,
        )

    base_params = {
        'type': tx_type,
        'q': query,
        'date_from': date_from_raw,
        'date_to': date_to_raw,
        'date_filter_mode': date_filter_mode,
        'date_value': date_value_raw,
        'date_start': date_start_raw,
        'date_end': date_end_raw,
        'show_codes': '1' if show_product_codes else '',
        'type_filter': type_filters,
        'description_filter': description_filters,
        'partner_filter': partner_filters,
        'payment_filter': payment_filters,
        'quantity_filter_mode': quantity_filter_mode,
        'quantity_value': quantity_value_raw,
        'quantity_min': quantity_min_raw,
        'quantity_max': quantity_max_raw,
        'amount_filter_mode': amount_filter_mode,
        'amount_value': amount_value_raw,
        'amount_min': amount_min_raw,
        'amount_max': amount_max_raw,
    }
    base_params = {key: value for key, value in base_params.items() if value}

    def build_query(overrides):
        params = base_params.copy()
        list_overrides = {}
        params.update({key: value for key, value in overrides.items() if value})
        for key, value in overrides.items():
            if isinstance(value, list):
                list_overrides[key] = value
                if not value:
                    params.pop(key, None)
            if value == '':
                params.pop(key, None)
        params.update(list_overrides)
        return f"?{urlencode(params, doseq=True)}"

    def date_range_query(start, end):
        return build_query({
            'date_from': start.isoformat(),
            'date_to': end.isoformat(),
            'date_filter_mode': '',
            'date_value': '',
            'date_start': '',
            'date_end': '',
        })

    today_start = today
    week_start = today - timedelta(days=6)
    month_start = today.replace(day=1)
    history_all_query = date_range_query(earliest_date, today)
    history_today_query = date_range_query(today_start, today)
    history_week_query = date_range_query(week_start, today)
    history_month_query = date_range_query(month_start, today)
    active_start = date_from.isoformat() if date_from else ''
    active_end = date_to.isoformat() if date_to else ''
    if active_start == earliest_date.isoformat() and active_end == today.isoformat():
        history_period = 'all'
    elif active_start == today_start.isoformat() and active_end == today.isoformat():
        history_period = 'today'
    elif active_start == week_start.isoformat() and active_end == today.isoformat():
        history_period = 'week'
    elif active_start == month_start.isoformat() and active_end == today.isoformat():
        history_period = 'month'
    else:
        history_period = 'custom'

    def short_list_label(values):
        if not values:
            return ''
        if len(values) == 1:
            return values[0]
        return f'{values[0]} +{len(values) - 1}'

    def date_label(value):
        parsed = parse_filter_date(value)
        return parsed.strftime('%d/%m/%Y') if parsed else value

    type_label_map = {option['value']: option['label'] for option in type_options}
    filter_badges = {
        'type': short_list_label([type_label_map.get(value, value) for value in type_filters]),
        'description': short_list_label(description_filters),
        'partner': short_list_label(partner_filters),
        'payment': short_list_label([dict(payment_options).get(value, value) for value in payment_filters]),
    }
    if date_filter_mode == 'before' and date_value_raw:
        filter_badges['date'] = f'Trước {date_label(date_value_raw)}'
    elif date_filter_mode == 'after' and date_value_raw:
        filter_badges['date'] = f'Sau {date_label(date_value_raw)}'
    elif date_filter_mode == 'range' and (date_start_raw or date_end_raw):
        filter_badges['date'] = f'{date_label(date_start_raw)} - {date_label(date_end_raw)}'

    number_filter_labels = {
        'eq': 'Bằng',
        'gt': '>',
        'lt': '<',
        'range': 'Trong khoảng',
    }
    if quantity_filter_mode:
        if quantity_filter_mode == 'range':
            filter_badges['quantity'] = f'{quantity_min_raw or "..."} - {quantity_max_raw or "..."}'
        elif quantity_value_raw:
            filter_badges['quantity'] = f'{number_filter_labels.get(quantity_filter_mode, "")} {quantity_value_raw}'
    if amount_filter_mode:
        if amount_filter_mode == 'range':
            filter_badges['amount'] = f'{amount_min_raw or "..."} - {amount_max_raw or "..."}'
        elif amount_value_raw:
            filter_badges['amount'] = f'{number_filter_labels.get(amount_filter_mode, "")} {amount_value_raw}'

    def sort_column(field, label, sort_kind='number'):
        filter_label = filter_badges.get(field, '')
        tooltip_suffix = f' Đang lọc: {filter_label}.' if filter_label else ''
        if sort_kind == 'text':
            asc_state = 'A-Z'
            desc_state = 'Z-A'
            first_tip = f'Chưa sắp xếp theo {label}. Ấn để sắp xếp A-Z.'
            asc_tip = f'Đang sắp xếp {label} A-Z. Ấn để đổi sang Z-A.'
            desc_tip = f'Đang sắp xếp {label} Z-A. Ấn để bỏ sắp xếp cột này.'
        elif sort_kind == 'date':
            asc_state = 'Cũ đến mới'
            desc_state = 'Mới đến cũ'
            first_tip = f'Chưa sắp xếp theo {label}. Ấn để sắp xếp từ cũ đến mới.'
            asc_tip = f'Đang sắp xếp {label} từ cũ đến mới. Ấn để đổi sang mới đến cũ.'
            desc_tip = f'Đang sắp xếp {label} từ mới đến cũ. Ấn để bỏ sắp xếp cột này.'
        else:
            asc_state = 'Thấp đến cao'
            desc_state = 'Cao đến thấp'
            first_tip = f'Chưa sắp xếp theo {label}. Ấn để sắp xếp từ thấp đến cao.'
            asc_tip = f'Đang sắp xếp {label} từ thấp đến cao. Ấn để đổi sang cao đến thấp.'
            desc_tip = f'Đang sắp xếp {label} từ cao đến thấp. Ấn để bỏ sắp xếp cột này.'
        if sort_field != field:
            next_url = build_query({'sort': field, 'dir': 'asc'})
            return {
                'field': field,
                'label': label,
                'url': next_url,
                'asc_url': next_url,
                'desc_url': build_query({'sort': field, 'dir': 'desc'}),
                'clear_url': build_query({'sort': '', 'dir': ''}),
                'icon': 'arrow-up-down',
                'active': False,
                'state': '',
                'tooltip': first_tip + tooltip_suffix,
                'filter_active': bool(filter_label),
                'filter_label': filter_label,
            }
        if sort_dir == 'asc':
            return {
                'field': field,
                'label': label,
                'url': build_query({'sort': field, 'dir': 'desc'}),
                'asc_url': build_query({'sort': field, 'dir': 'asc'}),
                'desc_url': build_query({'sort': field, 'dir': 'desc'}),
                'clear_url': build_query({'sort': '', 'dir': ''}),
                'icon': 'arrow-up',
                'active': True,
                'state': asc_state,
                'tooltip': asc_tip + tooltip_suffix,
                'filter_active': bool(filter_label),
                'filter_label': filter_label,
            }
        return {
            'field': field,
            'label': label,
            'url': build_query({'sort': '', 'dir': ''}),
            'asc_url': build_query({'sort': field, 'dir': 'asc'}),
            'desc_url': build_query({'sort': field, 'dir': 'desc'}),
            'clear_url': build_query({'sort': '', 'dir': ''}),
            'icon': 'arrow-down',
            'active': True,
            'state': desc_state,
            'tooltip': desc_tip + tooltip_suffix,
            'filter_active': bool(filter_label),
            'filter_label': filter_label,
        }

    sort_columns = [
        sort_column('type', 'Loại', 'text'),
        sort_column('date', 'Ngày', 'date'),
        sort_column('description', 'Nội dung', 'text'),
        sort_column('partner', 'Đối tác', 'text'),
        sort_column('quantity', 'Số lượng', 'number'),
        sort_column('amount', 'Giá trị', 'number'),
        sort_column('payment', 'Thanh toán', 'text'),
    ]
    type_links = {
        key: build_query({'type': key, 'type_filter': [], 'sort': sort_field, 'dir': sort_dir})
        for key in ('all', 'income', 'purchase', 'expense')
    }
    clear_filter_urls = {
        'all': '?type=all',
        'type': build_query({'type': 'all', 'type_filter': []}),
        'description': build_query({'description_filter': []}),
        'partner': build_query({'partner_filter': []}),
        'payment': build_query({'payment_filter': []}),
        'date': build_query({
            'date_from': '',
            'date_to': '',
            'date_filter_mode': '',
            'date_value': '',
            'date_start': '',
            'date_end': '',
        }),
        'quantity': build_query({
            'quantity_filter_mode': '',
            'quantity_value': '',
            'quantity_min': '',
            'quantity_max': '',
        }),
        'amount': build_query({
            'amount_filter_mode': '',
            'amount_value': '',
            'amount_min': '',
            'amount_max': '',
        }),
    }
    has_detail_summary_filter = any([
        query,
        tx_type != 'all',
        type_filters,
        description_filters,
        partner_filters,
        payment_filters,
        quantity_filter_mode,
        amount_filter_mode,
    ])
    if has_detail_summary_filter:
        recognized_income = sum(item['amount'] for item in transactions if item['amount'] > 0)
        recognized_out = abs(sum(item['amount'] for item in transactions if item['amount'] < 0))
        cash_income = sum(
            item['amount']
            for item in transactions
            if item['amount'] > 0 and item['payment_status']['key'] == 'paid'
        )
        cash_out = abs(sum(
            item['amount']
            for item in transactions
            if item['amount'] < 0 and item['payment_status']['key'] == 'paid'
        ))
    else:
        sales_for_summary = user_sales
        purchases_for_summary = user_purchases
        if date_from:
            sales_for_summary = sales_for_summary.filter(date__gte=date_from)
            purchases_for_summary = purchases_for_summary.filter(date__gte=date_from)
        if date_to:
            sales_for_summary = sales_for_summary.filter(date__lte=date_to)
            purchases_for_summary = purchases_for_summary.filter(date__lte=date_to)
        recognized_income = sales_for_summary.aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
        recognized_out = cogs_summary(date_from, date_to, request.user)['total'] + recognized_expense_summary(date_from, date_to, request.user)['total']
        cash_summary = cash_flow_summary(date_from, date_to, request.user)
        cash_income = cash_summary['income']
        cash_out = cash_summary['outflow']
    recognized_profit = recognized_income - recognized_out
    cash_net = cash_income - cash_out

    products = for_user(Product, request.user).filter(is_active=True).order_by('name')
    expense_type_choices = Expense.EXPENSE_TYPE_CHOICES

    return render(request, 'core/transaction_history.html', {
        'transactions': transactions,
        'tx_type': tx_type,
        'query': query,
        'date_from': date_from_raw,
        'date_to': date_to_raw,
        'date_filter_mode': date_filter_mode,
        'date_value': date_value_raw,
        'date_start': date_start_raw,
        'date_end': date_end_raw,
        'show_product_codes': show_product_codes,
        'type_options': type_options,
        'type_filters': type_filters,
        'description_options': description_options,
        'partner_options': partner_options,
        'payment_options': payment_options,
        'description_filters': description_filters,
        'partner_filters': partner_filters,
        'payment_filters': payment_filters,
        'quantity_filter_mode': quantity_filter_mode,
        'quantity_value': quantity_value_raw,
        'quantity_min': quantity_min_raw,
        'quantity_max': quantity_max_raw,
        'amount_filter_mode': amount_filter_mode,
        'amount_value': amount_value_raw,
        'amount_min': amount_min_raw,
        'amount_max': amount_max_raw,
        'sort_field': sort_field,
        'sort_dir': sort_dir,
        'sort_columns': sort_columns,
        'type_links': type_links,
        'clear_filter_urls': clear_filter_urls,
        'history_all_query': history_all_query,
        'history_today_query': history_today_query,
        'history_week_query': history_week_query,
        'history_month_query': history_month_query,
        'history_period': history_period,
        'recognized_income': recognized_income,
        'recognized_out': recognized_out,
        'recognized_profit': recognized_profit,
        'cash_income': cash_income,
        'cash_out': cash_out,
        'cash_net': cash_net,
        'products': products,
        'expense_type_choices': expense_type_choices,
    })


def transaction_page_context(user=None):
    today = timezone.now().date()
    yesterday = today - timedelta(days=1)
    sales = for_user(Sale, user) if user is not None else Sale.objects.all()
    expenses = for_user(Expense, user) if user is not None else Expense.objects.all()

    def percent_change(current, previous):
        if previous == 0:
            return None
        return round(((float(current) - float(previous)) / abs(float(previous))) * 100, 1)

    today_income = sales.filter(date=today).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
    today_cogs = cogs_summary(today, today, user)['total']
    today_expense = recognized_expense_summary(today, today, user)['total']
    today_cost = today_cogs + today_expense
    today_profit = today_income - today_cost

    yesterday_income = sales.filter(date=yesterday).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
    yesterday_cogs = cogs_summary(yesterday, yesterday, user)['total']
    yesterday_expense = recognized_expense_summary(yesterday, yesterday, user)['total']
    yesterday_cost = yesterday_cogs + yesterday_expense
    yesterday_profit = yesterday_income - yesterday_cost

    recent_sales = list(sales.select_related('product').order_by('-date', '-created_at')[:2])
    recent_expenses = list(expenses.order_by('-date', '-created_at')[:2])

    return {
        'today_income': today_income,
        'today_cost': today_cost,
        'today_profit': today_profit,
        'today_income_change': percent_change(today_income, yesterday_income),
        'today_cost_change': percent_change(today_cost, yesterday_cost),
        'today_profit_change': percent_change(today_profit, yesterday_profit),
        'recent_sales': recent_sales,
        'recent_expenses': recent_expenses,
    }


def dashboard_view(request):
    if request.method == 'POST' and request.POST.get('action') == 'update_payment_warning':
        try:
            request.session['payment_warning_days'] = max(0, min(int(request.POST.get('payment_warning_days', PAYMENT_WARNING_DAYS)), 60))
        except (TypeError, ValueError):
            request.session['payment_warning_days'] = PAYMENT_WARNING_DAYS
        return redirect('dashboard')
    if request.method == 'POST' and request.POST.get('action') in {'hide_initial_setup_reminder', 'hide_checklist'}:
        request.session['hide_checklist'] = True
        return redirect('dashboard')

    today = timezone.now().date()
    month_start = today.replace(day=1)
    user_products = for_user(Product, request.user)
    user_sales = for_user(Sale, request.user)
    user_purchases = for_user(Purchase, request.user)
    user_expenses = for_user(Expense, request.user)

    def parse_date(value, fallback):
        if not value:
            return fallback
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return fallback

    all_dates = []
    all_dates.extend(user_sales.values_list('date', flat=True))
    all_dates.extend(user_purchases.values_list('date', flat=True))
    all_dates.extend(user_expenses.values_list('date', flat=True))
    earliest_date = min(all_dates) if all_dates else today
    start_date = parse_date(request.GET.get('start_date'), month_start)
    end_date = parse_date(request.GET.get('end_date'), today)
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    week_start = today - timedelta(days=6)
    year_start = today.replace(month=1, day=1)
    requested_period = request.GET.get('period', '')
    if requested_period in {'all', 'today', 'week', 'month', 'year'}:
        active_period = requested_period
    elif start_date == month_start and end_date == today:
        active_period = 'month'
    elif start_date == year_start and end_date == today:
        active_period = 'year'
    elif start_date == today and end_date == today:
        active_period = 'today'
    elif start_date == week_start and end_date == today:
        active_period = 'week'
    elif start_date == earliest_date and end_date == today:
        active_period = 'all'
    else:
        active_period = 'custom'

    sales_in_range = user_sales.filter(date__gte=start_date, date__lte=end_date)
    purchases_in_range = user_purchases.filter(date__gte=start_date, date__lte=end_date)
    expenses_in_range = user_expenses.filter(date__gte=start_date, date__lte=end_date)

    total_income = sales_in_range.aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
    total_purchase = purchases_in_range.aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
    cogs_total = cogs_summary(start_date, end_date, request.user)['total']
    recognized_expenses = recognized_expense_summary(start_date, end_date, request.user)
    operating_expense_total = recognized_expenses['total']
    total_expense = operating_expense_total
    total_recognized_cost = cogs_total + operating_expense_total
    total_expense_all = total_recognized_cost
    cash_summary = cash_flow_summary(start_date, end_date, request.user)
    cash_income = cash_summary['income']
    cash_expense = cash_summary['expense_out']
    cash_purchase = cash_summary['purchase_out']
    cash_outflow = cash_summary['outflow']
    net_cash_flow = cash_summary['net']
    gross_profit = total_income - cogs_total
    net_profit = gross_profit - operating_expense_total
    estimated_profit = net_profit

    total_sales_count = sales_in_range.count()
    total_purchases_count = purchases_in_range.count()
    total_expenses_count = expenses_in_range.count()
    total_transactions = total_sales_count + total_purchases_count + total_expenses_count

    period_days = (end_date - start_date).days + 1
    if active_period == 'year':
        try:
            previous_start = start_date.replace(year=start_date.year - 1)
        except ValueError:
            previous_start = start_date.replace(year=start_date.year - 1, day=28)
        previous_end = previous_start + timedelta(days=period_days - 1)
    elif active_period == 'month':
        if start_date.month == 1:
            previous_start = start_date.replace(year=start_date.year - 1, month=12)
        else:
            previous_start = start_date.replace(month=start_date.month - 1)
        previous_end = previous_start + timedelta(days=period_days - 1)
    elif active_period == 'week':
        previous_end = start_date - timedelta(days=1)
        previous_start = previous_end - timedelta(days=6)
    elif active_period == 'today':
        previous_end = start_date - timedelta(days=1)
        previous_start = previous_end
    else:
        previous_end = start_date - timedelta(days=1)
        previous_start = previous_end - timedelta(days=period_days - 1)

    previous_income = user_sales.filter(date__gte=previous_start, date__lte=previous_end).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
    previous_purchase = user_purchases.filter(date__gte=previous_start, date__lte=previous_end).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
    previous_cogs = cogs_summary(previous_start, previous_end, request.user)['total']
    previous_cash_summary = cash_flow_summary(previous_start, previous_end, request.user)
    previous_expense = recognized_expense_summary(previous_start, previous_end, request.user)['total']
    previous_expense_all = previous_cogs + previous_expense
    previous_cash_flow = previous_cash_summary['net']
    previous_gross_profit = previous_income - previous_cogs
    previous_profit = previous_gross_profit - previous_expense
    has_comparison_data = any([
        previous_income,
        previous_cogs,
        previous_expense,
        previous_expense_all,
        previous_cash_flow,
        previous_profit,
    ])

    def percent_change(current, previous):
        if previous == 0:
            return None
        return round(((float(current) - float(previous)) / abs(float(previous))) * 100, 1)

    income_change = percent_change(total_income, previous_income)
    cogs_change = percent_change(cogs_total, previous_cogs)
    gross_profit_change = percent_change(gross_profit, previous_gross_profit)
    operating_expense_change = percent_change(operating_expense_total, previous_expense)
    expense_change = percent_change(total_expense_all, previous_expense_all)
    cash_flow_change = percent_change(net_cash_flow, previous_cash_flow)
    profit_change = percent_change(estimated_profit, previous_profit)

    today_sales = user_sales.filter(date=today).aggregate(total=Sum('total_amount'))['total'] or 0
    today_sales_count = user_sales.filter(date=today).count()
    today_purchases = user_purchases.filter(date=today).aggregate(total=Sum('total_amount'))['total'] or 0
    today_expenses = user_expenses.filter(date=today).aggregate(total=Sum('amount'))['total'] or 0

    # Product metrics
    total_products = user_products.filter(is_active=True).count()
    out_of_stock_products = user_products.filter(stock_quantity=0).filter(
        Q(purchases__isnull=False) | Q(opening_stocks__isnull=False)
    ).distinct()
    products_missing_stock = user_products.filter(
        is_active=True,
        stock_quantity=0,
        purchases__isnull=True,
        opening_stocks__isnull=True,
    ).distinct().order_by('name')
    low_stock_products = user_products.filter(
        stock_quantity__gt=0,
        stock_quantity__lte=F('alert_threshold')
    )
    alert_count = out_of_stock_products.count() + low_stock_products.count()

    # Recent transactions (sales, purchases, expenses)
    recent_sales = user_sales.select_related('product').order_by('-date', '-created_at')[:5]
    recent_purchases = user_purchases.select_related('product').order_by('-date', '-created_at')[:5]
    recent_expenses = user_expenses.order_by('-date', '-created_at')[:3]

    # This month metrics
    month_income = user_sales.filter(date__gte=month_start).aggregate(total=Sum('total_amount'))['total'] or 0
    month_purchase = user_purchases.filter(date__gte=month_start).aggregate(total=Sum('total_amount'))['total'] or 0
    month_expense_only = recognized_expense_summary(month_start, today, request.user)['total']
    month_cogs = cogs_summary(month_start, today, request.user)['total']
    month_expense = month_cogs + month_expense_only
    month_profit = month_income - month_expense
    month_sales_count = user_sales.filter(date__gte=month_start).count()

    daily_income = {
        item['date']: item['total'] or Decimal('0')
        for item in sales_in_range.values('date').annotate(total=Sum('total_amount'))
    }
    daily_purchase = {
        item['date']: item['total'] or Decimal('0')
        for item in purchases_in_range.values('date').annotate(total=Sum('total_amount'))
    }
    daily_expense = {
        item['date']: item['total'] or Decimal('0')
        for item in expenses_in_range.values('date').annotate(total=Sum('amount'))
    }
    daily_cogs = {
        item['date']: item['total'] or Decimal('0')
        for item in sales_in_range.values('date').annotate(total=Sum('cogs_amount'))
    }

    chart_data = []
    cursor = start_date
    while cursor <= end_date:
        income = daily_income.get(cursor, Decimal('0'))
        gross_profit_day = income - daily_cogs.get(cursor, Decimal('0'))
        cash_in = cash_summary['income_by_date'].get(cursor, Decimal('0'))
        cash_out = cash_summary['purchase_by_date'].get(cursor, Decimal('0')) + cash_summary['expense_by_date'].get(cursor, Decimal('0'))
        cash_net = cash_in - cash_out
        chart_data.append({
            'label': cursor.strftime('%d/%m'),
            'income': float(income),
            'gross_profit': float(gross_profit_day),
            'expense': float(cash_out),
            'profit': float(cash_net),
        })
        cursor += timedelta(days=1)

    avg_income_per_day = total_income / period_days if period_days else Decimal('0')
    avg_expense_per_day = total_expense_all / period_days if period_days else Decimal('0')
    avg_cash_out_per_day = cash_outflow / period_days if period_days else Decimal('0')
    gross_margin = round((float(gross_profit) / float(total_income)) * 100, 1) if total_income else 0
    has_products = total_products > 0
    has_transactions = total_transactions > 0
    has_opening_stock = for_user(OpeningStock, request.user).exists()
    has_viewed_report = bool(request.session.get('report_viewed'))
    onboarding_complete = has_products and has_transactions and has_viewed_report
    show_inventory_tip = bool(request.session.get('show_inventory_tip'))
    warning_days = payment_warning_days(request)
    payment_alerts = build_payment_alerts(warning_days, limit=5, user=request.user)

    if previous_start == previous_end:
        prev_dates = previous_start.strftime('%d/%m/%Y')
    else:
        prev_dates = f"{previous_start.strftime('%d/%m/%Y')} - {previous_end.strftime('%d/%m/%Y')}"

    if active_period == 'today':
        comparison_label = "Hôm qua"
        previous_period_text = f"so với hôm qua ({prev_dates})"
    elif active_period == 'week':
        comparison_label = "7 ngày trước đó"
        previous_period_text = f"so với 7 ngày trước đó ({prev_dates})"
    elif active_period == 'month':
        comparison_label = "Cùng số ngày đã qua của tháng trước"
        previous_period_text = f"so với cùng số ngày đã qua của tháng trước ({prev_dates})"
    elif active_period == 'year':
        comparison_label = "Cùng số ngày đã qua của năm ngoái"
        previous_period_text = f"so với cùng số ngày đã qua của năm ngoái ({prev_dates})"
    elif active_period == 'all':
        comparison_label = "Kỳ trước cùng số ngày"
        previous_period_text = f"so với kỳ trước cùng số ngày ({prev_dates})"
    else:
        comparison_label = "Kỳ trước cùng số ngày"
        previous_period_text = f"so với kỳ trước cùng số ngày ({prev_dates})"

    context = {
        # Financial metrics
        'total_income': total_income,
        'total_purchase': total_purchase,
        'total_expense': total_expense,
        'total_expense_all': total_expense_all,
        'recognized_revenue': total_income,
        'cogs': cogs_total,
        'gross_profit': gross_profit,
        'operating_expense': operating_expense_total,
        'net_profit': net_profit,
        'cash_in': cash_income,
        'cash_out': cash_outflow,
        'cash_expense': cash_expense,
        'cash_purchase': cash_purchase,
        'cash_income': cash_income,
        'cash_outflow': cash_outflow,
        'net_cash_flow': net_cash_flow,
        'estimated_profit': estimated_profit,
        'income_change': income_change,
        'cogs_change': cogs_change,
        'gross_profit_change': gross_profit_change,
        'operating_expense_change': operating_expense_change,
        'expense_change': expense_change,
        'cash_flow_change': cash_flow_change,
        'profit_change': profit_change,
        
        # Transaction counts
        'total_sales_count': total_sales_count,
        'total_purchases_count': total_purchases_count,
        'total_expenses_count': total_expenses_count,
        'total_transactions': total_transactions,
        
        # Product metrics
        'total_products': total_products,
        'out_of_stock_products': out_of_stock_products,
        'products_missing_stock': products_missing_stock,
        'products_missing_stock_count': products_missing_stock.count(),
        'low_stock_products': low_stock_products,
        'alert_count': alert_count,
        
        # Recent transactions
        'recent_sales': recent_sales,
        'recent_purchases': recent_purchases,
        'recent_expenses': recent_expenses,
        
        # Month metrics for banner
        'month_income': month_income,
        'month_purchase': month_purchase,
        'month_expense_only': month_expense_only,
        'month_profit': month_profit,
        'month_sales_count': month_sales_count,
        'start_date': start_date,
        'end_date': end_date,
        'date_range_label': f"{start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')}",
        'previous_period_label': f"{previous_start.strftime('%d/%m/%Y')} - {previous_end.strftime('%d/%m/%Y')}",
        'previous_period_text': previous_period_text,
        'comparison_label': comparison_label,
        'has_comparison_data': has_comparison_data,
        'today_query': f"period=today&start_date={today.isoformat()}&end_date={today.isoformat()}",
        'week_query': f"period=week&start_date={week_start.isoformat()}&end_date={today.isoformat()}",
        'month_query': f"period=month&start_date={month_start.isoformat()}&end_date={today.isoformat()}",
        'year_query': f"period=year&start_date={year_start.isoformat()}&end_date={today.isoformat()}",
        'all_query': f"period=all&start_date={earliest_date.isoformat()}&end_date={today.isoformat()}",
        'active_period': active_period,
        'chart_data': chart_data,
        'avg_income_per_day': avg_income_per_day,
        'avg_expense_per_day': avg_expense_per_day,
        'avg_cash_out_per_day': avg_cash_out_per_day,
        'gross_margin': gross_margin,
        'has_products': has_products,
        'has_transactions': has_transactions,
        'has_opening_stock': has_opening_stock,
        'has_viewed_report': has_viewed_report,
        'onboarding_complete': onboarding_complete,
        'show_initial_setup_reminder': not request.session.get('hide_checklist') and not onboarding_complete,
        'dashboard_empty': not has_products and not has_transactions,
        'show_inventory_tip': show_inventory_tip,
        'payment_warning_days': warning_days,
        'customer_payment_alerts': payment_alerts['customer_payment_alerts'],
        'supplier_payment_alerts': payment_alerts['supplier_payment_alerts'],
        'supplier_debt_count': payment_alerts['supplier_debt_count'],
    }
    return render(request, 'core/dashboard.html', context)

def report_view(request):
    request.session['report_viewed'] = True
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    profit_view_mode = request.GET.get('profit_view', 'category')
    profit_category_filter = request.GET.get('profit_category', '').strip()
    profit_rank = request.GET.get('profit_rank', 'top10')
    profit_granularity = request.GET.get('profit_granularity', 'month')
    if profit_granularity not in ('day', 'week', 'month', 'year'):
        profit_granularity = 'month'
    revenue_view_mode = request.GET.get('revenue_view', 'category')
    revenue_category_filter = request.GET.get('revenue_category', '').strip()
    revenue_rank = request.GET.get('revenue_rank', 'top10')
    revenue_granularity = request.GET.get('revenue_granularity', 'month')
    if revenue_granularity not in ('day', 'week', 'month', 'year'):
        revenue_granularity = 'month'
    cash_granularity = request.GET.get('cash_granularity', 'month')
    if cash_granularity not in ('day', 'week', 'month', 'year'):
        cash_granularity = 'month'
    expense_granularity = request.GET.get('expense_granularity', 'month')
    if expense_granularity not in ('day', 'month', 'year'):
        expense_granularity = 'month'

    user_products = for_user(Product, request.user)
    user_sales = for_user(Sale, request.user)
    user_purchases = for_user(Purchase, request.user)
    user_expenses = expenses_for_user(request.user)

    purchases = user_purchases
    sales = user_sales
    expenses = user_expenses
    all_expenses = user_expenses

    if start_date:
        purchases = purchases.filter(date__gte=start_date)
        sales = sales.filter(date__gte=start_date)
        expenses = expenses.filter(date__gte=start_date)

    if end_date:
        purchases = purchases.filter(date__lte=end_date)
        sales = sales.filter(date__lte=end_date)
        expenses = expenses.filter(date__lte=end_date)

    def parse_report_date(raw):
        if not raw:
            return None
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            return None

    def month_start(value):
        return datetime(value.year, value.month, 1).date()

    def add_months(value, months):
        month_index = value.month - 1 + months
        year = value.year + month_index // 12
        month = month_index % 12 + 1
        return datetime(year, month, 1).date()

    def month_count(start, end):
        if not start or not end or end < start:
            return 0
        return (end.year - start.year) * 12 + end.month - start.month + 1

    parsed_start_date = parse_report_date(start_date)
    parsed_end_date = parse_report_date(end_date)
    today = timezone.now().date()
    min_data_date = None
    report_end_date = parsed_end_date or today
    for candidate in [
        user_sales.order_by('date').values_list('date', flat=True).first(),
        user_purchases.order_by('date').values_list('date', flat=True).first(),
        user_expenses.order_by('date').values_list('date', flat=True).first(),
        report_end_date,
    ]:
        if candidate and (min_data_date is None or candidate < min_data_date):
            min_data_date = candidate
    report_start_date = parsed_start_date or min_data_date or report_end_date
    if report_start_date > report_end_date:
        report_start_date, report_end_date = report_end_date, report_start_date

    purchases = user_purchases.filter(date__gte=report_start_date, date__lte=report_end_date)
    sales = user_sales.filter(date__gte=report_start_date, date__lte=report_end_date)
    expenses = user_expenses.filter(date__gte=report_start_date, date__lte=report_end_date)

    report_effective_start = report_start_date
    report_days = max(1, (report_end_date - report_effective_start).days + 1)
    previous_report_end = report_effective_start - timedelta(days=1)
    previous_report_start = previous_report_end - timedelta(days=report_days - 1)

    def report_percent_change(current, previous):
        if previous == 0:
            return None
        return round(((float(current) - float(previous)) / abs(float(previous))) * 100, 1)

    def report_period_bounds(anchor_date, granularity):
        if granularity == 'day':
            start = anchor_date
            end = anchor_date
            previous_end = start - timedelta(days=1)
            previous_start = previous_end
        elif granularity == 'year':
            start = datetime(anchor_date.year, 1, 1).date()
            end = datetime(anchor_date.year, 12, 31).date()
            previous_start = datetime(anchor_date.year - 1, 1, 1).date()
            previous_end = datetime(anchor_date.year - 1, 12, 31).date()
        else:
            start = month_start(anchor_date)
            next_start = add_months(start, 1)
            end = next_start - timedelta(days=1)
            previous_start = add_months(start, -1)
            previous_end = start - timedelta(days=1)
        return start, end, previous_start, previous_end

    def report_period_label(value, granularity):
        if granularity == 'day':
            return value.strftime('%d/%m/%Y')
        if granularity == 'year':
            return f"Năm {value.year}"
        return value.strftime('T%m/%Y')

    expense_recognized_total = Decimal('0')
    expense_recognized_by_month = {}
    depreciation_end_limit = month_start(report_end_date)

    for expense in all_expenses:
        amount = Decimal(expense.amount or 0)
        if expense.estimated_lifetime_months:
            depreciation_start = month_start(expense.date)
            depreciation_end = add_months(depreciation_start, expense.estimated_lifetime_months - 1)
            period_start = month_start(report_start_date) if report_start_date else depreciation_start
            period_end = depreciation_end_limit
            overlap_start = max(depreciation_start, period_start)
            overlap_end = min(depreciation_end, period_end)
            months = month_count(overlap_start, overlap_end)
            if months <= 0:
                continue
            monthly_amount = amount / Decimal(expense.estimated_lifetime_months)
            recognized_amount = monthly_amount * months
            current_month = overlap_start
            while current_month <= overlap_end:
                key = current_month.strftime('%Y-%m')
                expense_recognized_by_month[key] = expense_recognized_by_month.get(key, Decimal('0')) + monthly_amount
                current_month = add_months(current_month, 1)
        else:
            if report_start_date and expense.date < report_start_date:
                continue
            if report_end_date and expense.date > report_end_date:
                continue
            recognized_amount = amount
            key = month_start(expense.date).strftime('%Y-%m')
            expense_recognized_by_month[key] = expense_recognized_by_month.get(key, Decimal('0')) + amount

        expense_recognized_total += recognized_amount

    total_income = sales.aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
    recognized_revenue = total_income
    previous_report_income = user_sales.filter(date__gte=previous_report_start, date__lte=previous_report_end).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
    if previous_report_income:
        revenue_total_growth = round(((total_income - previous_report_income) / abs(previous_report_income)) * 100, 1)
    else:
        revenue_total_growth = 0
    cash_summary = cash_flow_summary(report_start_date, report_end_date, request.user)
    cash_income = cash_summary['income']
    cash_expense = cash_summary['expense_out']
    cash_purchase = cash_summary['purchase_out']
    cogs_data = cogs_summary(report_start_date, report_end_date, request.user)
    cogs = cogs_data['total']
    cogs_by_month = cogs_data['by_month']
    operating_expense = expense_recognized_total
    cash_outflow = cash_summary['outflow']
    net_cash_flow = cash_summary['net']
    gross_profit = recognized_revenue - cogs
    profit = gross_profit - operating_expense
    net_profit = profit
    expense_labels = dict(Expense.EXPENSE_TYPE_CHOICES)
    revenue_order_count = sales.count()
    revenue_orders_per_day = round(revenue_order_count / report_days, 1) if report_days else 0
    revenue_avg_order_value = (recognized_revenue / Decimal(revenue_order_count)) if revenue_order_count else Decimal('0')
    revenue_collected = cash_income
    unpaid_sales = sales.filter(payment_method=Sale.PAYMENT_METHOD_DEBT)
    revenue_uncollected = unpaid_sales.aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
    revenue_uncollected_order_count = unpaid_sales.count()
    revenue_collection_rate = round((revenue_collected / recognized_revenue) * 100, 1) if recognized_revenue else 0
    top_revenue_product = (
        sales.values('product__name', 'product__unit')
        .annotate(units=Sum('quantity'), revenue=Sum('total_amount'))
        .order_by('-revenue')
        .first()
    )
    top_revenue_category = (
        sales.exclude(product__category='')
        .values('product__category')
        .annotate(revenue=Sum('total_amount'))
        .order_by('-revenue')
        .first()
    )

    chart_sales = sales
    if revenue_category_filter:
        chart_sales = chart_sales.filter(product__category__startswith=revenue_category_filter)

    sales_by_month = (
        chart_sales.annotate(month=TruncMonth('date'))
        .values('month')
        .annotate(total=Sum('total_amount'))
        .order_by('month')
    )

    purchases_by_month = (
        purchases.annotate(month=TruncMonth('date'))
        .values('month')
        .annotate(total=Sum('total_amount'))
        .order_by('month')
    )

    month_map = {}

    for item in sales_by_month:
        key = item['month'].strftime('%Y-%m')
        month_map.setdefault(key, {'income': 0, 'purchase': 0, 'expense': 0})
        month_map[key]['income'] = float(item['total'] or 0)

    for key, total in cogs_by_month.items():
        month_map.setdefault(key, {'income': 0, 'purchase': 0, 'expense': 0})
        month_map[key]['purchase'] = float(total or 0)

    for key, total in expense_recognized_by_month.items():
        month_map.setdefault(key, {'income': 0, 'purchase': 0, 'expense': 0})
        month_map[key]['expense'] = float(total or 0)

    chart_labels = sorted(month_map.keys())
    chart_income = [month_map[m]['income'] for m in chart_labels]
    chart_purchase = [month_map[m]['purchase'] for m in chart_labels]
    chart_expense = [month_map[m]['expense'] for m in chart_labels]
    chart_gross_profit = [
        month_map[m]['income'] - month_map[m]['purchase']
        for m in chart_labels
    ]
    chart_profit = chart_gross_profit
    revenue_trend_rows = []
    previous_trend_revenue = None
    previous_trend_gross_profit = None
    for label in chart_labels:
        period_revenue = Decimal(str(month_map.get(label, {}).get('income', 0)))
        period_cogs = cogs_by_month.get(label, Decimal('0'))
        period_gross_profit = period_revenue - period_cogs
        revenue_growth = None
        gross_profit_growth = None
        if previous_trend_revenue not in (None, Decimal('0')):
            revenue_growth = round(((period_revenue - previous_trend_revenue) / abs(previous_trend_revenue)) * 100, 1)
        if previous_trend_gross_profit not in (None, Decimal('0')):
            gross_profit_growth = round(((period_gross_profit - previous_trend_gross_profit) / abs(previous_trend_gross_profit)) * 100, 1)
        revenue_trend_rows.append({
            'label': label,
            'revenue': period_revenue,
            'cogs': period_cogs,
            'gross_profit': period_gross_profit,
            'revenue_growth': revenue_growth,
            'gross_profit_growth': gross_profit_growth,
        })
        previous_trend_revenue = period_revenue
        previous_trend_gross_profit = period_gross_profit

    def revenue_period_key(value):
        if revenue_granularity == 'day':
            return value.strftime('%Y-%m-%d')
        if revenue_granularity == 'week':
            iso_year, iso_week, _ = value.isocalendar()
            return f'{iso_year}-W{iso_week:02d}'
        if revenue_granularity == 'year':
            return value.strftime('%Y')
        return value.strftime('%Y-%m')

    def revenue_period_label(key):
        if revenue_granularity == 'day':
            try:
                return datetime.strptime(key, '%Y-%m-%d').strftime('%d/%m/%Y')
            except ValueError:
                return key
        if revenue_granularity == 'week':
            return key.replace('-W', ' Tuần ')
        if revenue_granularity == 'year':
            return f'Năm {key}'
        try:
            return datetime.strptime(key, '%Y-%m').strftime('T%m/%Y')
        except ValueError:
            return key

    revenue_period_map = {}
    for sale in sales.select_related('product'):
        key = revenue_period_key(sale.date)
        bucket = revenue_period_map.setdefault(key, {
            'revenue': Decimal('0'),
            'orders': 0,
        })
        bucket['revenue'] += sale.total_amount or Decimal('0')
        bucket['orders'] += 1
    revenue_chart_points = [
        {
            'key': key,
            'label': revenue_period_label(key),
            'revenue': float(revenue_period_map[key]['revenue']),
            'orders': revenue_period_map[key]['orders'],
            'avg_order': float(
                revenue_period_map[key]['revenue'] / Decimal(revenue_period_map[key]['orders'])
            ) if revenue_period_map[key]['orders'] else 0,
        }
        for key in sorted(revenue_period_map.keys())
    ]
    revenue_chart_points_json = json.dumps(revenue_chart_points)
    revenue_time_rows = [
        {
            'label': item['label'],
            'revenue': Decimal(str(item['revenue'])),
            'orders': item['orders'],
            'avg_order': Decimal(str(item['avg_order'])),
        }
        for item in revenue_chart_points
    ]

    def profit_period_key(value):
        if profit_granularity == 'day':
            return value.strftime('%Y-%m-%d')
        if profit_granularity == 'week':
            iso_year, iso_week, _ = value.isocalendar()
            return f'{iso_year}-W{iso_week:02d}'
        if profit_granularity == 'year':
            return value.strftime('%Y')
        return value.strftime('%Y-%m')

    def profit_period_label(key):
        if profit_granularity == 'day':
            try:
                return datetime.strptime(key, '%Y-%m-%d').strftime('%d/%m/%Y')
            except ValueError:
                return key
        if profit_granularity == 'week':
            return key.replace('-W', ' Tuần ')
        if profit_granularity == 'year':
            return f'Năm {key}'
        try:
            return datetime.strptime(key, '%Y-%m').strftime('T%m/%Y')
        except ValueError:
            return key

    profit_period_map = {}
    for sale in sales.select_related('product'):
        key = profit_period_key(sale.date)
        bucket = profit_period_map.setdefault(key, {
            'revenue': Decimal('0'),
            'cogs': Decimal('0'),
            'operating_expense': Decimal('0'),
        })
        bucket['revenue'] += sale.total_amount or Decimal('0')
        bucket['cogs'] += sale.cogs_amount or Decimal('0')
    for key, amount in expense_recognized_by_month.items():
        try:
            expense_date = datetime.strptime(key, '%Y-%m').date()
        except ValueError:
            expense_date = report_start_date
        bucket = profit_period_map.setdefault(profit_period_key(expense_date), {
            'revenue': Decimal('0'),
            'cogs': Decimal('0'),
            'operating_expense': Decimal('0'),
        })
        bucket['operating_expense'] += amount or Decimal('0')
    profit_time_chart_points = []
    for key in sorted(profit_period_map.keys()):
        bucket = profit_period_map[key]
        period_gross_profit = bucket['revenue'] - bucket['cogs']
        profit_time_chart_points.append({
            'key': key,
            'label': profit_period_label(key),
            'revenue': float(bucket['revenue']),
            'cogs': float(bucket['cogs']),
            'gross_profit': float(period_gross_profit),
            'operating_expense': float(bucket['operating_expense']),
            'net_profit': float(period_gross_profit - bucket['operating_expense']),
        })
    profit_time_chart_points_json = json.dumps(profit_time_chart_points)

    cash_month_map = {}
    def cash_period_key(value):
        if cash_granularity == 'day':
            return value.strftime('%Y-%m-%d')
        if cash_granularity == 'week':
            iso_year, iso_week, _ = value.isocalendar()
            return f'{iso_year}-W{iso_week:02d}'
        if cash_granularity == 'year':
            return value.strftime('%Y')
        return value.strftime('%Y-%m')

    def cash_period_label(key):
        if cash_granularity == 'day':
            try:
                return datetime.strptime(key, '%Y-%m-%d').strftime('%d/%m/%Y')
            except ValueError:
                return key
        if cash_granularity == 'week':
            return key.replace('-W', ' Tuần ')
        if cash_granularity == 'year':
            return f'Năm {key}'
        try:
            return datetime.strptime(key, '%Y-%m').strftime('T%m/%Y')
        except ValueError:
            return key

    def cash_period_range(key):
        if cash_granularity == 'day':
            try:
                start = datetime.strptime(key, '%Y-%m-%d').date()
            except ValueError:
                start = report_start_date
            end = start
        elif cash_granularity == 'week':
            try:
                iso_year, iso_week = key.split('-W')
                start = datetime.fromisocalendar(int(iso_year), int(iso_week), 1).date()
            except (TypeError, ValueError):
                start = report_start_date
            end = start + timedelta(days=6)
        elif cash_granularity == 'year':
            try:
                start = datetime(int(key), 1, 1).date()
            except ValueError:
                start = report_start_date
            end = datetime(start.year, 12, 31).date()
        else:
            try:
                start = datetime.strptime(key, '%Y-%m').date()
            except ValueError:
                start = report_start_date
            end = add_months(start, 1) - timedelta(days=1)
        return max(start, report_start_date), min(end, report_end_date)

    def cash_bucket(key):
        return cash_month_map.setdefault(key, {
            'in': 0.0,
            'out': 0.0,
            'purchase_out': 0.0,
            'opex_out': 0.0,
            'equipment_out': 0.0,
            'out_parts': {},
            'income_count': 0,
            'purchase_count': 0,
            'opex_count': 0,
            'equipment_count': 0,
        })

    def add_cash_out_part(bucket, label, amount):
        amount = float(amount or 0)
        if not amount:
            return
        bucket['out_parts'][label] = bucket['out_parts'].get(label, 0.0) + amount

    for cash_date, amount in cash_summary['income_by_date'].items():
        key = cash_period_key(cash_date)
        cash_bucket(key)['in'] += float(amount or 0)
    for cash_date, amount in cash_summary['purchase_by_date'].items():
        key = cash_period_key(cash_date)
        bucket = cash_bucket(key)
        bucket['out'] += float(amount or 0)
        bucket['purchase_out'] += float(amount or 0)
    for cash_date, amount in cash_summary['expense_by_date'].items():
        key = cash_period_key(cash_date)
        bucket = cash_bucket(key)
        bucket['out'] += float(amount or 0)

    for sale in user_sales.select_related('product').exclude(payment_method=Sale.PAYMENT_METHOD_DEBT):
        cash_date = sale.payment_date or sale.date
        if cash_date < report_start_date or cash_date > report_end_date:
            continue
        key = cash_period_key(cash_date)
        bucket = cash_bucket(key)
        bucket['income_count'] += 1

    for purchase in user_purchases.select_related('product').exclude(payment_method=Purchase.PAYMENT_METHOD_DEBT):
        cash_date = purchase.payment_date or purchase.date
        if cash_date < report_start_date or cash_date > report_end_date:
            continue
        key = cash_period_key(cash_date)
        bucket = cash_bucket(key)
        bucket['purchase_count'] += 1
        add_cash_out_part(bucket, 'Nhập hàng', purchase.total_amount or Decimal('0'))

    for expense in user_expenses.exclude(payment_method=Expense.PAYMENT_METHOD_DEBT):
        cash_date = expense.payment_date or expense.date
        if cash_date < report_start_date or cash_date > report_end_date:
            continue
        key = cash_period_key(cash_date)
        bucket = cash_bucket(key)
        amount = float(expense.amount or Decimal('0'))
        if expense.expense_type == Expense.EXPENSE_TYPE_EQUIPMENT:
            bucket['equipment_out'] += amount
            bucket['equipment_count'] += 1
        else:
            bucket['opex_out'] += amount
            bucket['opex_count'] += 1
        label = expense_labels.get(expense.expense_type, expense.expense_type)
        if expense.expense_type == 'other':
            note_label = (expense.note or '').strip().splitlines()[0]
            if note_label:
                label = note_label[:60]
        add_cash_out_part(bucket, label, expense.amount or Decimal('0'))

    for bucket in cash_month_map.values():
        expense_out = bucket['opex_out'] + bucket['equipment_out']
        if expense_out:
            bucket['out'] = bucket['purchase_out'] + expense_out
    cash_chart_labels = sorted(cash_month_map.keys())
    cash_chart_in = [cash_month_map[m]['in'] for m in cash_chart_labels]
    cash_chart_out = [cash_month_map[m]['out'] for m in cash_chart_labels]
    cash_chart_net = [cash_month_map[m]['in'] - cash_month_map[m]['out'] for m in cash_chart_labels]
    cash_chart_points = []
    for label in cash_chart_labels:
        period_start, period_end = cash_period_range(label)
        cash_out_total = cash_month_map[label]['out']
        cash_out_parts = [
            {
                'label': name,
                'amount': value,
                'share': round((value / cash_out_total * 100), 1) if cash_out_total else 0,
            }
            for name, value in sorted(cash_month_map[label]['out_parts'].items(), key=lambda item: item[1], reverse=True)
        ]
        cash_chart_points.append({
            'key': label,
            'label': cash_period_label(label),
            'date_from': period_start.isoformat(),
            'date_to': period_end.isoformat(),
            'history_in_url': f"/transactions/history/?{urlencode({'type': 'income', 'type_filter': ['income'], 'date_from': period_start.isoformat(), 'date_to': period_end.isoformat()}, doseq=True)}",
            'history_out_url': f"/transactions/history/?{urlencode({'type': 'all', 'type_filter': ['purchase', 'expense'], 'date_from': period_start.isoformat(), 'date_to': period_end.isoformat()}, doseq=True)}",
            'cash_in': cash_month_map[label]['in'],
            'cash_out': cash_month_map[label]['out'],
            'net': cash_month_map[label]['in'] - cash_month_map[label]['out'],
            'breakdown': {
                'purchase': cash_month_map[label]['purchase_out'],
                'opex': cash_month_map[label]['opex_out'],
                'equipment': cash_month_map[label]['equipment_out'],
            },
            'out_parts': cash_out_parts,
            'counts': {
                'income': cash_month_map[label]['income_count'],
                'purchase': cash_month_map[label]['purchase_count'],
                'opex': cash_month_map[label]['opex_count'],
                'equipment': cash_month_map[label]['equipment_count'],
            },
        })
    cash_chart_rows = []
    running_cash_balance = Decimal('0')
    for label in cash_chart_labels:
        cash_in_value = Decimal(str(cash_month_map[label]['in']))
        cash_out_value = Decimal(str(cash_month_map[label]['out']))
        net_value = cash_in_value - cash_out_value
        running_cash_balance += net_value
        period_recognized_revenue = Decimal(str(month_map.get(label, {}).get('income', 0)))
        collection_rate = round((cash_in_value / period_recognized_revenue) * 100, 1) if period_recognized_revenue else None
        cash_chart_rows.append({
            'label': label,
            'cash_in': cash_in_value,
            'cash_out': cash_out_value,
            'net': net_value,
            'running_balance': running_cash_balance,
            'collection_rate': collection_rate,
        })

    cash_burn_per_day = (max(cash_outflow - cash_income, Decimal('0')) / Decimal(report_days)) if report_days else Decimal('0')
    cash_runway_days = round((cash_income / cash_burn_per_day), 1) if cash_burn_per_day > 0 else None
    cash_income_per_day = cash_income / Decimal(report_days) if report_days else Decimal('0')
    cash_conversion_rate = round((cash_income / recognized_revenue) * 100, 1) if recognized_revenue else 0
    cash_purchase_share = round((cash_purchase / cash_outflow) * 100, 1) if cash_outflow else 0
    cash_opex_share = round((cash_expense / cash_outflow) * 100, 1) if cash_outflow else 0
    cash_out_revenue_ratio = round((cash_outflow / recognized_revenue), 2) if recognized_revenue else 0

    payable_purchase_debt = user_purchases.filter(payment_method=Purchase.PAYMENT_METHOD_DEBT).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
    payable_expense_debt = user_expenses.filter(payment_method=Expense.PAYMENT_METHOD_DEBT).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    payable_debt = payable_purchase_debt + payable_expense_debt
    upcoming_payable_deadline = today + timedelta(days=7)
    upcoming_purchase_payable = user_purchases.filter(
        payment_method=Purchase.PAYMENT_METHOD_DEBT,
        payment_due_date__isnull=False,
        payment_due_date__lte=upcoming_payable_deadline,
    ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
    upcoming_expense_payable = user_expenses.filter(
        payment_method=Expense.PAYMENT_METHOD_DEBT,
        payment_due_date__isnull=False,
        payment_due_date__lte=upcoming_payable_deadline,
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    upcoming_payable = upcoming_purchase_payable + upcoming_expense_payable
    next_payable_item = None
    next_purchase_due = user_purchases.filter(
        payment_method=Purchase.PAYMENT_METHOD_DEBT,
        payment_due_date__isnull=False,
    ).order_by('payment_due_date', '-created_at').first()
    next_expense_due = user_expenses.filter(
        payment_method=Expense.PAYMENT_METHOD_DEBT,
        payment_due_date__isnull=False,
    ).order_by('payment_due_date', '-created_at').first()
    due_candidates = []
    if next_purchase_due:
        due_candidates.append((next_purchase_due.payment_due_date, next_purchase_due.total_amount or Decimal('0'), next_purchase_due.supplier_name or 'Nhà cung cấp'))
    if next_expense_due:
        due_candidates.append((next_expense_due.payment_due_date, next_expense_due.amount or Decimal('0'), expense_labels.get(next_expense_due.expense_type, 'Chi phí')))
    if due_candidates:
        due_date, due_amount, due_label = sorted(due_candidates, key=lambda item: item[0])[0]
        next_payable_item = {'date': due_date, 'amount': due_amount, 'label': due_label}

    def category_parts(path):
        return [part.strip() for part in (path or '').split('/') if part.strip()]

    def safe_sale_product(sale):
        try:
            return sale.product
        except Product.DoesNotExist:
            return None

    def sale_category_parts(sale):
        product = safe_sale_product(sale)
        return category_parts(getattr(product, 'category', '')) or ['Hàng hóa']

    def sale_product_name(sale):
        product = safe_sale_product(sale)
        return getattr(product, 'name', 'Sản phẩm')

    if revenue_category_filter:
        revenue_sales = sales.filter(product__category__startswith=revenue_category_filter)
    else:
        revenue_sales = sales

    revenue_node_map = {}
    def ensure_revenue_node(path, level, name):
        node = revenue_node_map.get(path)
        if not node:
            node = {
                'name': name,
                'path': path,
                'level': level,
                'total': Decimal('0'),
                'cogs': Decimal('0'),
                'quantity': 0,
                'profit': Decimal('0'),
                'growth': 0,
                'revenue_share': 0,
                'profit_share': 0,
                'children': {},
                'children_list': [],
            }
            revenue_node_map[path] = node
            if level > 1:
                parent_path = ' / '.join(path.split(' / ')[:-1])
                parent = revenue_node_map.get(parent_path)
                if parent:
                    parent['children'][name] = node
                    parent['children_list'].append(node)
        return node

    revenue_roots = []
    for sale in revenue_sales.select_related('product'):
        parts = sale_category_parts(sale)
        revenue = sale.total_amount or Decimal('0')
        cost = sale.cogs_amount or Decimal('0')
        sale_profit = revenue - cost
        path_parts = []
        for level, part in enumerate(parts[:4], start=1):
            path_parts.append(part)
            node_path = ' / '.join(path_parts)
            node = ensure_revenue_node(node_path, level, part)
            if level == 1 and node not in revenue_roots:
                revenue_roots.append(node)
            node['total'] += revenue
            node['cogs'] += cost
            node['quantity'] += sale.quantity or 0
            node['profit'] += sale_profit

    revenue_by_category = []
    revenue_group_field = 'product__name' if revenue_view_mode == 'product' else 'product__category'
    revenue_values = [revenue_group_field]
    if revenue_view_mode == 'product':
        revenue_values += ['product__unit']
    category_sales = (
        revenue_sales.values(*revenue_values)
        .annotate(total=Sum('total_amount'), units=Sum('quantity'), cogs_total=Sum('cogs_amount'))
        .order_by('-total')
    )
    
    category_sales_list = list(category_sales)
    if revenue_rank == 'top10':
        category_sales_list = category_sales_list[:10]
    elif revenue_rank == 'bottom10':
        category_sales_list = sorted(category_sales_list, key=lambda x: x['total'] or Decimal('0'))[:10]
    
    for item in category_sales_list:
        total = item['total'] or Decimal('0')
        share = round((total / total_income * 100), 1) if total_income else 0
        row_cost = item['cogs_total'] or Decimal('0')
        row_profit = total - row_cost
        profit_share = round((row_profit / gross_profit * 100), 1) if gross_profit else 0
        quantity = item['units'] or 0
        revenue_by_category.append({
            'name': item[revenue_group_field] or 'Hàng hóa',
            'unit': item.get('product__unit') or 'đơn vị',
            'quantity': quantity,
            'total': total,
            'cogs': row_cost,
            'profit': row_profit,
            'share': share,
            'profit_share': profit_share,
            'growth': 0,
        })

    for node in revenue_node_map.values():
        node['revenue_share'] = round((node['total'] / total_income * 100), 1) if total_income else 0
        node['profit_share'] = round((node['profit'] / gross_profit * 100), 1) if gross_profit else 0

    revenue_contribution_rows = revenue_by_category
    max_contribution_value = max(
        [abs(item['total']) for item in revenue_contribution_rows] + [abs(item['profit']) for item in revenue_contribution_rows] + [Decimal('0')]
    )
    revenue_contribution_chart_rows = []
    for item in revenue_contribution_rows:
        revenue_width = int(round(abs(item['total']) / max_contribution_value * 100)) if max_contribution_value else 0
        profit_width = int(round(abs(item['profit']) / max_contribution_value * 100)) if max_contribution_value else 0
        revenue_w = max(3, revenue_width) if item['total'] else 0
        profit_w = max(3, profit_width) if item['profit'] else 0
        revenue_contribution_chart_rows.append({
            **item,
            'revenue_width': revenue_w,
            'profit_width': profit_w,
            'revenue_opacity': round(0.36 + (revenue_w * 0.0064), 2),
            'profit_opacity': round(0.36 + (profit_w * 0.0064), 2),
        })

    revenue_insight_cards = []
    top_revenue_contributor = max(revenue_contribution_rows, key=lambda item: item['total'], default=None)
    top_profit_contributor = max(revenue_contribution_rows, key=lambda item: item['profit'], default=None)
    if top_revenue_contributor:
        revenue_insight_cards.append({
            'title': 'Doanh thu cao nhất',
            'body': f"{top_revenue_contributor['name']} tạo {top_revenue_contributor['total']:,.0f}đ doanh thu trong kỳ.".replace(',', '.'),
        })
    if top_profit_contributor:
        revenue_insight_cards.append({
            'title': 'Đóng góp lợi nhuận gộp cao nhất',
            'body': f"{top_profit_contributor['name']} tạo {top_profit_contributor['profit']:,.0f}đ lợi nhuận gộp.".replace(',', '.'),
        })
    if len(revenue_trend_rows) >= 2:
        latest_trend = revenue_trend_rows[-1]
        revenue_word = 'tăng' if (latest_trend['revenue_growth'] or 0) >= 0 else 'giảm'
        profit_word = 'tăng' if (latest_trend['gross_profit_growth'] or 0) >= 0 else 'giảm'
        revenue_insight_cards.append({
            'title': 'Xu hướng kỳ gần nhất',
            'body': f"Doanh thu {revenue_word} {abs(latest_trend['revenue_growth'] or 0)}%, lợi nhuận gộp {profit_word} {abs(latest_trend['gross_profit_growth'] or 0)}% so với kỳ trước.",
        })

    contribution_node_map = {}
    contribution_roots = []

    def contribution_metric_dict(name, path='', level=0, kind='category', unit='đơn vị'):
        return {
            'name': name,
            'path': path,
            'level': level,
            'kind': kind,
            'unit': unit,
            'quantity': 0,
            'revenue': Decimal('0'),
            'cogs': Decimal('0'),
            'gross_profit': Decimal('0'),
            'children': {},
            'children_list': [],
            'products': [],
        }

    def ensure_contribution_node(path, level, name):
        node = contribution_node_map.get(path)
        if not node:
            node = contribution_metric_dict(name, path, level)
            contribution_node_map[path] = node
            if level == 1:
                contribution_roots.append(node)
            else:
                parent_path = ' / '.join(path.split(' / ')[:-1])
                parent = contribution_node_map.get(parent_path)
                if parent:
                    parent['children'][name] = node
                    parent['children_list'].append(node)
        return node

    for sale in sales.select_related('product'):
        parts = sale_category_parts(sale)
        revenue = sale.total_amount or Decimal('0')
        cost = sale.cogs_amount or Decimal('0')
        path_parts = []
        for level, part in enumerate(parts[:4], start=1):
            path_parts.append(part)
            path = ' / '.join(path_parts)
            node = ensure_contribution_node(path, level, part)
            node['quantity'] += sale.quantity or 0
            node['revenue'] += revenue
            node['cogs'] += cost
            node['gross_profit'] += revenue - cost

    product_contribution_rows = []
    product_contribution_source = (
        sales.values('product_id', 'product__name', 'product__category', 'product__unit')
        .annotate(total=Sum('total_amount'), units=Sum('quantity'), cogs_total=Sum('cogs_amount'))
        .order_by('-total')
    )
    for item in product_contribution_source:
        product_parts = category_parts(item.get('product__category')) or ['Hàng hóa']
        parent_path = ' / '.join(product_parts[:4])
        revenue = item['total'] or Decimal('0')
        cogs_value = item['cogs_total'] or Decimal('0')
        product_row = contribution_metric_dict(
            item.get('product__name') or 'Sản phẩm',
            f"{parent_path} / SP-{item['product_id']}",
            min(len(product_parts[:4]) + 1, 5),
            'product',
            item.get('product__unit') or 'đơn vị',
        )
        product_row['parent_path'] = parent_path
        product_row['quantity'] = item['units'] or 0
        product_row['revenue'] = revenue
        product_row['cogs'] = cogs_value
        product_row['gross_profit'] = revenue - cogs_value
        product_contribution_rows.append(product_row)
        parent_node = contribution_node_map.get(parent_path)
        if parent_node is not None:
            parent_node['products'].append(product_row)

    def contribution_share(value, total):
        return float(round((value / total * 100), 1)) if total else 0.0

    def serialize_contribution_row(row):
        return {
            'name': row['name'],
            'path': row.get('path', ''),
            'parent_path': row.get('parent_path', ''),
            'kind': row.get('kind', 'category'),
            'unit': row.get('unit', 'đơn vị'),
            'quantity': row.get('quantity', 0),
            'revenue': float(row.get('revenue') or Decimal('0')),
            'cogs': float(row.get('cogs') or Decimal('0')),
            'gross_profit': float(row.get('gross_profit') or Decimal('0')),
            'revenue_share': contribution_share(row.get('revenue') or Decimal('0'), recognized_revenue),
            'profit_share': contribution_share(row.get('gross_profit') or Decimal('0'), gross_profit),
            'children': [serialize_contribution_row(child) for child in row.get('children_list', [])],
            'products': [serialize_contribution_row(product) for product in row.get('products', [])],
        }

    revenue_contribution_data_json = json.dumps({
        'roots': [serialize_contribution_row(node) for node in contribution_roots],
        'products': [serialize_contribution_row(product) for product in product_contribution_rows],
        'totals': {
            'revenue': float(recognized_revenue or Decimal('0')),
            'cogs': float(cogs or Decimal('0')),
            'gross_profit': float(gross_profit or Decimal('0')),
        },
    })

    expense_labels = dict(Expense.EXPENSE_TYPE_CHOICES)

    def expense_period_key(value):
        if expense_granularity == 'day':
            return value.strftime('%Y-%m-%d')
        if expense_granularity == 'year':
            return value.strftime('%Y')
        return value.strftime('%Y-%m')

    def expense_period_label(key):
        if expense_granularity == 'day':
            try:
                return datetime.strptime(key, '%Y-%m-%d').strftime('%d/%m/%Y')
            except ValueError:
                return key
        if expense_granularity == 'year':
            return f'Năm {key}'
        try:
            return datetime.strptime(key, '%Y-%m').strftime('T%m/%Y')
        except ValueError:
            return key

    expense_period_map = {}

    def expense_bucket(key):
        return expense_period_map.setdefault(key, {
            'total': Decimal('0'),
            'breakdown': {},
        })

    def add_expense_period_amount(value_date, name, amount):
        if not amount:
            return
        key = expense_period_key(value_date)
        bucket = expense_bucket(key)
        bucket['total'] += amount
        bucket['breakdown'][name] = bucket['breakdown'].get(name, Decimal('0')) + amount

    for sale in sales:
        add_expense_period_amount(sale.date, 'Giá vốn hàng bán', Decimal(sale.cogs_amount or 0))

    for expense in all_expenses:
        amount = Decimal(expense.amount or 0)
        label = expense_labels.get(expense.expense_type, expense.expense_type)
        if expense.estimated_lifetime_months:
            depreciation_start = month_start(expense.date)
            depreciation_end = add_months(depreciation_start, expense.estimated_lifetime_months - 1)
            period_start = month_start(report_start_date) if report_start_date else depreciation_start
            period_end = depreciation_end_limit
            overlap_start = max(depreciation_start, period_start)
            overlap_end = min(depreciation_end, period_end)
            monthly_amount = amount / Decimal(expense.estimated_lifetime_months)
            current_month = overlap_start
            while current_month <= overlap_end:
                add_expense_period_amount(current_month, label, monthly_amount)
                current_month = add_months(current_month, 1)
        else:
            if report_start_date and expense.date < report_start_date:
                continue
            if report_end_date and expense.date > report_end_date:
                continue
            add_expense_period_amount(expense.date, label, amount)

    expense_chart_points = []
    for key in sorted(expense_period_map.keys()):
        total = expense_period_map[key]['total']
        breakdown = [
            {
                'label': name,
                'amount': float(value),
                'share': round((value / total * 100), 1) if total else 0,
            }
            for name, value in sorted(expense_period_map[key]['breakdown'].items(), key=lambda item: item[1], reverse=True)
        ]
        expense_chart_points.append({
            'key': key,
            'label': expense_period_label(key),
            'total': float(total),
            'breakdown': breakdown,
        })

    expense_period_start, expense_period_end, expense_previous_start, expense_previous_end = report_period_bounds(report_end_date, expense_granularity)
    expense_period_label = report_period_label(expense_period_start, expense_granularity)
    expense_previous_label = report_period_label(expense_previous_start, expense_granularity)
    expense_period_days = max(1, (expense_period_end - expense_period_start).days + 1)
    expense_period_cogs = cogs_summary(expense_period_start, expense_period_end, request.user)['total']
    expense_period_summary = recognized_expense_summary(expense_period_start, expense_period_end, request.user)
    expense_period_total = expense_period_cogs + expense_period_summary['total']
    expense_period_revenue = user_sales.filter(date__gte=expense_period_start, date__lte=expense_period_end).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
    expense_per_day = expense_period_total / Decimal(expense_period_days) if expense_period_days else Decimal('0')
    expense_to_revenue_pct = round(float(expense_period_total / expense_period_revenue * 100), 1) if expense_period_revenue else None
    previous_cogs = cogs_summary(expense_previous_start, expense_previous_end, request.user)['total']
    previous_expense_summary = recognized_expense_summary(expense_previous_start, expense_previous_end, request.user)
    expense_previous_total = previous_cogs + previous_expense_summary['total']
    expense_total_change = report_percent_change(expense_period_total, expense_previous_total)
    expense_total_change_display = (
        str(round(expense_total_change, 1)).replace('.', ',')
        if expense_total_change is not None else None
    )
    previous_expense_by_key = {'cogs': previous_cogs, **previous_expense_summary['by_type']}
    current_expense_by_key = {'cogs': expense_period_cogs, **expense_period_summary['by_type']}
    comparison_keys = sorted(
        set(current_expense_by_key.keys()) | set(previous_expense_by_key.keys()),
        key=lambda item: current_expense_by_key.get(item, Decimal('0')),
        reverse=True,
    )
    comparison_max = max(
        [current_expense_by_key.get(key, Decimal('0')) for key in comparison_keys]
        + [previous_expense_by_key.get(key, Decimal('0')) for key in comparison_keys]
        + [Decimal('1')]
    )
    expense_comparison_rows = []
    for key in comparison_keys:
        current_total = current_expense_by_key.get(key, Decimal('0'))
        previous_total = previous_expense_by_key.get(key, Decimal('0'))
        if not current_total and not previous_total:
            continue
        row_change = report_percent_change(current_total, previous_total)
        is_allocated = key == Expense.EXPENSE_TYPE_EQUIPMENT
        if is_allocated:
            badge_label = 'Phân bổ'
            badge_tone = 'neutral'
        elif previous_total == 0 and current_total > 0:
            badge_label = 'Mới phát sinh'
            badge_tone = 'warning'
        elif current_total == 0 and previous_total > 0:
            badge_label = 'Đã dừng'
            badge_tone = 'neutral'
        elif row_change is not None and row_change >= float(EXPENSE_DELTA_HIGH_THRESHOLD):
            badge_label = f"+{str(round(row_change, 1)).replace('.', ',')}%"
            badge_tone = 'bad'
        elif row_change is not None and row_change > 0:
            badge_label = f"+{str(round(row_change, 1)).replace('.', ',')}%"
            badge_tone = 'muted'
        elif row_change is not None and row_change < 0:
            badge_label = f"{str(round(row_change, 1)).replace('.', ',')}%"
            badge_tone = 'good'
        else:
            badge_label = '0%'
            badge_tone = 'muted'
        expense_comparison_rows.append({
            'key': key,
            'name': 'Giá vốn hàng bán' if key == 'cogs' else expense_labels.get(key, key),
            'current_total': current_total,
            'previous_total': previous_total,
            'current_width': round(float(current_total / comparison_max * 100), 1) if comparison_max else 0,
            'previous_width': round(float(previous_total / comparison_max * 100), 1) if comparison_max else 0,
            'change': row_change,
            'is_allocated': is_allocated,
            'badge_label': badge_label,
            'badge_tone': badge_tone,
        })

    expense_period_breakdown = []
    if expense_period_cogs:
        expense_period_breakdown.append({
            'key': 'cogs',
            'name': 'Giá vốn hàng bán',
            'total': expense_period_cogs,
            'share': round((expense_period_cogs / expense_period_total * 100), 1) if expense_period_total else 0,
        })
    for expense_type, total in sorted(expense_period_summary['by_type'].items(), key=lambda item: item[1], reverse=True):
        expense_period_breakdown.append({
            'key': expense_type,
            'name': expense_labels.get(expense_type, expense_type),
            'total': total,
            'share': round((total / expense_period_total * 100), 1) if expense_period_total else 0,
        })

    if expense_to_revenue_pct is None:
        expense_to_revenue_display = '—'
        expense_to_revenue_note = 'Chưa có doanh thu kỳ này'
        expense_to_revenue_tone = 'neutral'
    elif Decimal(str(expense_to_revenue_pct)) < EXPENSE_RATIO_ATTENTION_THRESHOLD:
        expense_to_revenue_display = f"{str(expense_to_revenue_pct).replace('.', ',')}%"
        expense_to_revenue_note = 'Đang kiểm soát tốt'
        expense_to_revenue_tone = 'neutral'
    elif Decimal(str(expense_to_revenue_pct)) <= EXPENSE_RATIO_LOSS_THRESHOLD:
        expense_to_revenue_display = f"{str(expense_to_revenue_pct).replace('.', ',')}%"
        expense_to_revenue_note = 'Cần chú ý'
        expense_to_revenue_tone = 'danger'
    else:
        expense_to_revenue_display = f"{str(expense_to_revenue_pct).replace('.', ',')}%"
        expense_to_revenue_note = 'Đang lỗ — chi vượt doanh thu'
        expense_to_revenue_tone = 'danger'

    expense_alert = None
    if (
        expense_to_revenue_pct is not None
        and Decimal(str(expense_to_revenue_pct)) >= EXPENSE_RATIO_LOSS_THRESHOLD
    ):
        expense_alert = (
            f"Chi phí đang vượt doanh thu ({expense_to_revenue_display}) — "
            "Rà nhóm chi lớn nhất hoặc tăng doanh thu kỳ tới."
        )
    elif (
        expense_previous_total > 0
        and expense_period_total > expense_previous_total * EXPENSE_SPIKE_MULTIPLIER
    ):
        expense_alert = (
            f"Chi phí kỳ này tăng +{expense_total_change_display}% "
            "so với kỳ trước — Kiểm tra các khoản phát sinh mới."
        )

    expense_insight = None
    dominant_group = max(expense_period_breakdown, key=lambda item: item['share'], default=None)
    if (
        dominant_group
        and Decimal(str(dominant_group['share'])) >= EXPENSE_CATEGORY_DOMINANCE_THRESHOLD
    ):
        expense_insight = (
            f"{dominant_group['name']} chiếm {str(dominant_group['share']).replace('.', ',')}% "
            f"tổng chi phí kỳ này — cao bất thường. Kiểm tra {dominant_group['name'].lower()} liên quan."
        )
    else:
        new_groups = [
            row for row in expense_comparison_rows
            if row['previous_total'] == 0 and row['current_total'] > 0
        ]
        if new_groups:
            new_group_details = ', '.join(
                f"{row['name']} ({row['current_total']:,.0f} đ)".replace(',', '.')
                for row in new_groups
            )
            if len(new_groups) == 1:
                expense_insight = (
                    f"{new_group_details} mới phát sinh kỳ này "
                    "— chưa có dữ liệu kỳ trước để so sánh."
                )
            else:
                expense_insight = (
                    f"Các nhóm chi phí mới phát sinh kỳ này: {new_group_details} "
                    "— chưa có dữ liệu kỳ trước để so sánh."
                )
        else:
            comparable_groups = [
                row for row in expense_comparison_rows
                if row['previous_total'] > 0 and row['current_total'] > 0
            ]
            if comparable_groups and all(row['current_total'] > row['previous_total'] for row in comparable_groups):
                expense_insight = (
                    "Tất cả nhóm chi phí đều tăng so với kỳ trước — "
                    "Xem lại cơ cấu chi phí tổng thể."
                )

    equipment_depreciation_rows = []
    for expense in all_expenses.filter(expense_type=Expense.EXPENSE_TYPE_EQUIPMENT).order_by('-date', '-created_at'):
        if not expense.estimated_lifetime_months:
            continue
        amount = Decimal(expense.amount or 0)
        depreciation_start = month_start(expense.date)
        depreciation_end = add_months(depreciation_start, expense.estimated_lifetime_months - 1)
        overlap_start = max(depreciation_start, month_start(expense_period_start))
        overlap_end = min(depreciation_end, month_start(expense_period_end))
        recognized_months = month_count(overlap_start, overlap_end)
        if recognized_months <= 0 and depreciation_end < month_start(expense_period_start):
            continue
        monthly_amount = amount / Decimal(expense.estimated_lifetime_months)
        allocated_months = month_count(depreciation_start, min(depreciation_end, month_start(expense_period_end)))
        allocated_total = min(monthly_amount * allocated_months, amount)
        remaining = max(amount - allocated_total, Decimal('0'))
        months_left = max(expense.estimated_lifetime_months - allocated_months, 0)
        note_title = (expense.note or '').strip().splitlines()[0] if expense.note else ''
        equipment_depreciation_rows.append({
            'name': note_title or f"Thiết bị #{expense.id}",
            'date': expense.date,
            'amount': amount,
            'monthly_amount': monthly_amount,
            'recognized_amount': monthly_amount * recognized_months,
            'allocated_total': allocated_total,
            'remaining': remaining,
            'months_left': months_left,
            'progress_pct': round(float(allocated_total / amount * 100), 1) if amount else 0,
            'lifetime_months': expense.estimated_lifetime_months,
        })

    expense_period_day_note = f"Tính theo {expense_period_days} ngày · {expense_period_label}"

    category_option_tree = []
    category_nodes = {}
    category_filter_paths = set(
        user_products.filter(is_active=True).exclude(category='').values_list('category', flat=True)
    )
    category_filter_paths.update(
        sales.exclude(product__category='').values_list('product__category', flat=True)
    )
    for path in sorted(category_filter_paths):
        parts = category_parts(path)
        children = category_nodes
        branch = category_option_tree
        path_parts = []
        for level, part in enumerate(parts[:4], start=1):
            path_parts.append(part)
            node_path = ' / '.join(path_parts)
            node = children.get(part)
            if not node:
                node = {
                    'name': part,
                    'path': node_path,
                    'level': level,
                    'children': {},
                    'children_list': [],
                }
                children[part] = node
                branch.append(node)
            children = node['children']
            branch = node['children_list']

    profit_node_map = {}
    def ensure_profit_node(path, level, name):
        node = profit_node_map.get(path)
        if not node:
            node = {
                'name': name,
                'path': path,
                'level': level,
                'kind': 'category',
                'unit': 'đơn vị',
                'quantity_label': 'đơn vị',
                'revenue': Decimal('0'),
                'cogs': Decimal('0'),
                'quantity': 0,
                'profit': Decimal('0'),
                'margin': 0,
                'avg_price': Decimal('0'),
                'avg_cost': Decimal('0'),
                'profit_per_unit': Decimal('0'),
                'children': {},
                'children_list': [],
                'products': [],
            }
            profit_node_map[path] = node
            if level > 1:
                parent_path = ' / '.join(path.split(' / ')[:-1])
                parent = profit_node_map.get(parent_path)
                if parent:
                    parent['children'][name] = node
                    parent['children_list'].append(node)
        return node

    profit_roots = []
    for sale in sales.select_related('product'):
        parts = sale_category_parts(sale)
        if profit_category_filter and not ' / '.join(parts).startswith(profit_category_filter):
            continue
        revenue = sale.total_amount or Decimal('0')
        cost = sale.cogs_amount or Decimal('0')
        row_profit = revenue - cost
        path_parts = []
        for level, part in enumerate(parts[:4], start=1):
            path_parts.append(part)
            node_path = ' / '.join(path_parts)
            node = ensure_profit_node(node_path, level, part)
            if level == 1 and node not in profit_roots:
                profit_roots.append(node)
            node['revenue'] += revenue
            node['cogs'] += cost
            node['quantity'] += sale.quantity or 0
            node['profit'] += row_profit
    for node in profit_node_map.values():
        node['margin'] = round((node['profit'] / node['revenue'] * 100), 1) if node['revenue'] else 0
        if node['quantity']:
            quantity_decimal = Decimal(node['quantity'])
            node['avg_price'] = node['revenue'] / quantity_decimal
            node['avg_cost'] = node['cogs'] / quantity_decimal
            node['profit_per_unit'] = node['profit'] / quantity_decimal

    product_margin_rows_all = []
    product_margin_source = (
        sales.values('product_id', 'product__name', 'product__category', 'product__unit')
        .annotate(total=Sum('total_amount'), units=Sum('quantity'), cogs_total=Sum('cogs_amount'))
        .order_by('-total')
    )
    if profit_category_filter:
        product_margin_source = product_margin_source.filter(product__category__startswith=profit_category_filter)
    for item in product_margin_source:
        revenue = item['total'] or Decimal('0')
        quantity = item['units'] or 0
        cogs_total = item['cogs_total'] or Decimal('0')
        gross_profit_value = revenue - cogs_total
        quantity_decimal = Decimal(quantity) if quantity else Decimal('0')
        product_category_parts = category_parts(item.get('product__category')) or ['Hàng hóa']
        product_category_path = ' / '.join(product_category_parts[:4])
        product_unit = item.get('product__unit') or 'đơn vị'
        product_row = {
            'name': item.get('product__name') or 'Sản phẩm',
            'path': f"{product_category_path} / SP-{item['product_id']}",
            'parent_path': product_category_path,
            'kind': 'product',
            'unit': product_unit,
            'quantity_label': product_unit,
            'level': min(len(product_category_parts[:4]) + 1, 5),
            'quantity': quantity,
            'revenue': revenue,
            'cogs': cogs_total,
            'avg_price': (revenue / quantity_decimal) if quantity_decimal else Decimal('0'),
            'avg_cost': (cogs_total / quantity_decimal) if quantity_decimal else Decimal('0'),
            'profit': gross_profit_value,
            'profit_per_unit': (gross_profit_value / quantity_decimal) if quantity_decimal else Decimal('0'),
            'margin': round((gross_profit_value / revenue * 100), 1) if revenue else 0,
        }
        product_margin_rows_all.append(product_row)
        parent_node = profit_node_map.get(product_category_path)
        if parent_node is not None:
            parent_node['products'].append(product_row)

    margin_rows_all = []
    if profit_view_mode == 'product':
        margin_rows_all = list(product_margin_rows_all)
    else:
        if profit_category_filter:
            target_node = profit_node_map.get(profit_category_filter)
            nodes_to_compare = target_node['children_list'] if target_node else []
            if target_node and not nodes_to_compare:
                nodes_to_compare = [target_node]
        else:
            nodes_to_compare = profit_roots

        for node in nodes_to_compare:
            margin_rows_all.append({
                'name': node['name'],
                'kind': 'category',
                'unit': 'đơn vị',
                'quantity_label': 'đơn vị',
                'quantity': node['quantity'],
                'revenue': node['revenue'],
                'cogs': node['cogs'],
                'avg_price': node['avg_price'],
                'avg_cost': node['avg_cost'],
                'profit': node['profit'],
                'profit_per_unit': node['profit_per_unit'],
                'margin': node['margin'],
            })

    margin_total_revenue = sum(item['revenue'] for item in margin_rows_all)
    margin_total_profit = sum(item['profit'] for item in margin_rows_all)
    margin_total_quantity = sum(item['quantity'] for item in margin_rows_all)
    average_margin = round((margin_total_profit / margin_total_revenue * 100), 1) if margin_total_revenue else 0
    average_profit_per_unit = (margin_total_profit / Decimal(margin_total_quantity)) if margin_total_quantity else Decimal('0')
    average_quantity = (Decimal(margin_total_quantity) / Decimal(len(margin_rows_all))) if margin_rows_all else Decimal('0')

    def margin_suggestion(row):
        if row['profit'] < 0:
            return 'Đang bán lỗ', 'loss'
        high_margin = row['margin'] >= average_margin
        high_quantity = Decimal(row['quantity'] or 0) >= average_quantity
        if high_margin and high_quantity:
            return 'Sản phẩm chủ lực về biên', 'core'
        if high_margin and not high_quantity:
            return 'Cơ hội đẩy bán', 'potential'
        if not high_margin and high_quantity:
            return 'Bán nhiều nhưng lời mỏng', 'thin'
        return 'Cần xem lại giá vốn/giá bán', 'review'

    seen_row_ids = set()
    for row in [*profit_node_map.values(), *product_margin_rows_all, *margin_rows_all]:
        if id(row) in seen_row_ids:
            continue
        seen_row_ids.add(id(row))
        suggestion, suggestion_key = margin_suggestion(row)
        row['suggestion'] = suggestion
        row['suggestion_key'] = suggestion_key
        row['revenue_share'] = round((row['revenue'] / margin_total_revenue * 100), 1) if margin_total_revenue else 0
        row['profit_share'] = round((row['profit'] / margin_total_profit * 100), 1) if margin_total_profit else 0

    margin_sort_reverse = profit_rank != 'bottom10'
    
    # 1. BIÊN LỢI NHUẬN (Margin)
    profit_margin_rows = sorted([item for item in margin_rows_all if item['revenue'] > 0], key=lambda item: (item['margin'], item['profit_per_unit']), reverse=margin_sort_reverse)
    if profit_rank != 'all':
        profit_margin_rows = profit_margin_rows[:10]

    max_margin_abs = max([abs(float(item['margin'])) for item in profit_margin_rows] or [0])
    profit_chart_rows = []
    for item in profit_margin_rows:
        width = int(round(abs(float(item['margin'])) / max_margin_abs * 100)) if max_margin_abs else 0
        bar_width = max(3, width) if item['margin'] else 0
        profit_chart_rows.append({
            **item,
            'bar_width': bar_width,
            'bar_opacity': round(0.36 + (bar_width * 0.0064), 2),
            'is_negative': item['margin'] < 0 or item['profit'] < 0,
        })

    rankable_margin = [item for item in margin_rows_all if item['revenue'] > 0]
    best_margin_row = max(rankable_margin, key=lambda item: item['margin'], default=None)
    worst_margin_row = min(rankable_margin, key=lambda item: item['margin'], default=None)
    margin_kpis = {
        'average_margin': average_margin,
        'average_profit_per_unit': average_profit_per_unit,
        'best': best_margin_row,
        'worst': worst_margin_row,
    }

    margin_insight_cards = []
    if best_margin_row and best_margin_row['quantity'] > 0:
        margin_insight_cards.append({
            'title': f"{best_margin_row['name']} - Cơ hội đẩy bán",
            'body': f"Biên lợi nhuận cao nhất ({best_margin_row['margin']}%) nhưng số lượng bán chỉ {best_margin_row['quantity']}.",
        })
    thin_item = next((item for item in margin_rows_all if item.get('suggestion_key') == 'thin'), None)
    if thin_item:
        margin_insight_cards.append({
            'title': f"{thin_item['name']} - Bán nhiều nhưng lời mỏng",
            'body': f"SL bán cao ({thin_item['quantity']}) nhưng Biên lợi nhuận chỉ {thin_item['margin']}%.",
        })
    loss_item = next((item for item in margin_rows_all if item['profit'] < 0), None)
    if loss_item:
        margin_insight_cards.append({
            'title': f"{loss_item['name']} - Đang bán lỗ",
            'body': f"Lợi nhuận gộp âm {abs(loss_item['profit'])}. Cần xem lại giá vốn/giá bán.",
        })

    # 2. ĐÓNG GÓP LỢI NHUẬN (Contribution)
    profit_contribution_rows = sorted(margin_rows_all, key=lambda item: item['profit'], reverse=margin_sort_reverse)
    if profit_rank != 'all':
        profit_contribution_rows = profit_contribution_rows[:10]

    max_contribution_abs = max([abs(float(item['profit'])) for item in profit_contribution_rows] or [0])
    contribution_chart_rows = []
    for item in profit_contribution_rows:
        width = int(round(abs(float(item['profit'])) / max_contribution_abs * 100)) if max_contribution_abs else 0
        bar_width = max(3, width) if item['profit'] else 0
        contribution_chart_rows.append({
            **item,
            'bar_width': bar_width,
            'bar_opacity': round(0.36 + (bar_width * 0.0064), 2),
            'is_negative': item['profit'] < 0,
        })

    top_contrib_product = next((item for item in sorted(product_margin_rows_all, key=lambda x: x['profit'], reverse=True) if item['profit'] > 0), None)
    top_contrib_category = next((item for item in sorted(profit_node_map.values(), key=lambda x: x['profit'], reverse=True) if item['profit'] > 0), None)
    loss_items = [item for item in margin_rows_all if item['profit'] < 0]
    worst_loss_item = min(loss_items, key=lambda item: item['profit'], default=None) if loss_items else None
    
    contribution_kpis = {
        'top_product': top_contrib_product,
        'top_category': top_contrib_category,
        'loss_count': len(loss_items),
        'worst_loss': worst_loss_item,
    }

    contribution_insight_cards = []
    if top_contrib_product:
        contribution_insight_cards.append({
            'title': f"{top_contrib_product['name']} - Sản phẩm chủ lực",
            'body': f"Chiếm {top_contrib_product['profit_share']}% tổng lợi nhuận gộp toàn kỳ.",
        })
    if top_contrib_category and profit_view_mode == 'category':
        contribution_insight_cards.append({
            'title': f"{top_contrib_category['name']} - Danh mục đóng góp chính",
            'body': f"Chiếm {top_contrib_category['profit_share']}% tổng lợi nhuận gộp toàn kỳ.",
        })
    high_rev_low_profit = next((item for item in margin_rows_all if item['revenue_share'] > 10 and item['profit_share'] < 5), None)
    if high_rev_low_profit:
        contribution_insight_cards.append({
            'title': f"{high_rev_low_profit['name']} - Doanh thu cao nhưng lợi nhuận thấp",
            'body': f"Chiếm {high_rev_low_profit['revenue_share']}% doanh thu nhưng chỉ đóng góp {high_rev_low_profit['profit_share']}% lợi nhuận.",
        })

    profit_tree_roots = profit_roots
    if profit_category_filter:
        selected_profit_node = profit_node_map.get(profit_category_filter)
        profit_tree_roots = [selected_profit_node] if selected_profit_node else []

    top_product = (
        sales.values('product__name')
        .annotate(units=Sum('quantity'), revenue=Sum('total_amount'))
        .order_by('-units')
        .first()
    )
    top_customer = (
        sales.values('customer_name')
        .annotate(amount=Sum('total_amount'))
        .order_by('-amount')
        .first()
    )
    paid_sales_count = sales.exclude(payment_method=Sale.PAYMENT_METHOD_DEBT).count()
    ranking_revenue = {
        'best_product': {
            'name': top_product['product__name'],
            'orders': top_product['units'],
        } if top_product else None,
        'top_customer': {
            'name': (top_customer.get('customer_name') or 'Khách lẻ'),
            'amount': top_customer['amount'],
        } if top_customer else None,
        'top_category': {
            'name': top_revenue_category['product__category'],
            'amount': top_revenue_category['revenue'],
        } if top_revenue_category else None,
        'paid_ratio': {
            'pct': round(paid_sales_count / revenue_order_count * 100, 1),
            'paid': paid_sales_count,
            'total': revenue_order_count,
        } if revenue_order_count else None,
    }

    best_profit_category = max(
        (item for item in profit_node_map.values() if item['revenue'] > 0),
        key=lambda item: item['margin'],
        default=None,
    )
    best_profit_period = (
        max(profit_time_chart_points, key=lambda item: item['net_profit'], default=None)
        if (recognized_revenue or operating_expense) and profit_time_chart_points else None
    )

    
   
    ranking_profit = {
        'best_product': top_contrib_product,
        'worst_margin': worst_margin_row,
        'best_category_margin': best_profit_category,
        'best_period': {
            'label': best_profit_period['label'],   # <-- dùng 'label' thay vì 'period_label'
            'profit': best_profit_period['net_profit'],
        } if best_profit_period else None,
    }

    period_end_for_presets = today
    preset_1w_start = period_end_for_presets - timedelta(days=6)
    preset_1m_start = add_months(period_end_for_presets, -1)
    preset_3m_start = add_months(period_end_for_presets, -2)
    preset_6m_start = add_months(period_end_for_presets, -5)
    preset_12m_start = add_months(period_end_for_presets, -11)
    preserved_filter_query = urlencode({
        'revenue_view': revenue_view_mode,
        'revenue_category': revenue_category_filter,
        'revenue_rank': revenue_rank,
        'revenue_granularity': revenue_granularity,
        'profit_granularity': profit_granularity,
        'cash_granularity': cash_granularity,
        'expense_granularity': expense_granularity,
        'profit_view': profit_view_mode,
        'profit_category': profit_category_filter,
        'profit_rank': profit_rank,
    })

    return render(request, 'core/report.html', {
        'start_date': report_start_date.isoformat(),
        'end_date': report_end_date.isoformat(),
        'preset_1w_start': preset_1w_start,
        'preset_1m_start': preset_1m_start,
        'preset_3m_start': preset_3m_start,
        'preset_6m_start': preset_6m_start,
        'preset_12m_start': preset_12m_start,
        'period_end_for_presets': period_end_for_presets,
        'preserved_filter_query': preserved_filter_query,
        'total_income': total_income,
        'recognized_revenue': recognized_revenue,
        'revenue_total_growth': revenue_total_growth,
        'revenue_granularity': revenue_granularity,
        'profit_granularity': profit_granularity,
        'revenue_order_count': revenue_order_count,
        'revenue_orders_per_day': revenue_orders_per_day,
        'revenue_avg_order_value': revenue_avg_order_value,
        'revenue_collected': revenue_collected,
        'revenue_uncollected': revenue_uncollected,
        'revenue_uncollected_order_count': revenue_uncollected_order_count,
        'revenue_collection_rate': revenue_collection_rate,
        'top_revenue_product': top_revenue_product,
        'revenue_chart_points_json': revenue_chart_points_json,
        'revenue_time_rows': revenue_time_rows,
        'operating_expense': operating_expense,
        'cogs': cogs,
        'cash_expense': cash_expense,
        'cash_purchase': cash_purchase,
        'cash_income': cash_income,
        'cash_in': cash_income,
        'cash_outflow': cash_outflow,
        'cash_out': cash_outflow,
        'net_cash_flow': net_cash_flow,
        'cash_burn_per_day': cash_burn_per_day,
        'cash_runway_days': cash_runway_days,
        'cash_income_per_day': cash_income_per_day,
        'cash_conversion_rate': cash_conversion_rate,
        'cash_purchase_share': cash_purchase_share,
        'cash_opex_share': cash_opex_share,
        'cash_out_revenue_ratio': cash_out_revenue_ratio,
        'payable_debt': payable_debt,
        'upcoming_payable': upcoming_payable,
        'next_payable_item': next_payable_item,
        'gross_profit': gross_profit,
        'profit': profit,
        'net_profit': net_profit,
        'profit_time_chart_points_json': profit_time_chart_points_json,
        'cash_chart_points': cash_chart_points,
        'cash_chart_rows': cash_chart_rows,
        'revenue_by_category': revenue_by_category,
        'revenue_contribution_chart_rows': revenue_contribution_chart_rows,
        'revenue_contribution_data_json': revenue_contribution_data_json,
        'revenue_insight_cards': revenue_insight_cards,
        'revenue_roots': revenue_roots,
        'expense_chart_points': expense_chart_points,
        'expense_period_label': expense_period_label,
        'expense_previous_label': expense_previous_label,
        'expense_period_total': expense_period_total,
        'expense_period_day_note': expense_period_day_note,
        'expense_total_change': expense_total_change,
        'expense_total_change_display': expense_total_change_display,
        'expense_per_day': expense_per_day,
        'expense_to_revenue_display': expense_to_revenue_display,
        'expense_to_revenue_note': expense_to_revenue_note,
        'expense_to_revenue_tone': expense_to_revenue_tone,
        'expense_alert': expense_alert,
        'expense_comparison_rows': expense_comparison_rows,
        'expense_insight': expense_insight,
        'equipment_depreciation_rows': equipment_depreciation_rows,
        'profit_chart_rows': profit_chart_rows,
        'margin_kpis': margin_kpis,
        'margin_insight_cards': margin_insight_cards,
        'contribution_chart_rows': contribution_chart_rows,
        'contribution_kpis': contribution_kpis,
        'contribution_insight_cards': contribution_insight_cards,
        'profit_view_mode': profit_view_mode,
        'profit_tree_auto_expand': profit_view_mode == 'product',
        'profit_category_filter': profit_category_filter,
        'profit_rank': profit_rank,
        'revenue_view_mode': revenue_view_mode,
        'revenue_category_filter': revenue_category_filter,
        'revenue_rank': revenue_rank,
        'cash_granularity': cash_granularity,
        'expense_granularity': expense_granularity,
        'category_option_tree': category_option_tree,
        'profit_tree_roots': profit_tree_roots,
        'report_days': report_days,
        'ranking_revenue': ranking_revenue,
        'ranking_profit': ranking_profit,
    })


for _view_name in [
    'onboarding_welcome_view',
    'opening_stock_wizard_view',
    'setup_products_view',
    'dashboard_view',
    'inventory_view',
    'inventory_inline_update_view',
    'inventory_category_bulk_move_view',
    'inventory_category_delete_view',
    'inventory_category_create_view',
    'inventory_category_rename_view',
    'product_delete_view',
    'sale_new_product_ajax_view',
    'expense_new_product_ajax_view',
    'product_create_view',
    'purchase_delete_view',
    'purchase_edit_view',
    'sale_delete_view',
    'sale_edit_view',
    'sale_create_view',
    'expense_delete_view',
    'expense_edit_view',
    'expense_create_view',
    'transaction_create_view',
    'mark_transaction_paid_view',
    'extend_transaction_due_view',
    'bulk_transaction_create_view',
    'transaction_history_view',
    'report_view',
]:
    globals()[_view_name] = login_required(globals()[_view_name])

