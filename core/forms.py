from django import forms
from django.contrib.auth.forms import PasswordChangeForm

from .models import Product, Purchase, Sale, Expense


class AccountPasswordChangeForm(PasswordChangeForm):
    old_password = forms.CharField(
        label="Mật khẩu hiện tại",
        strip=False,
        widget=forms.PasswordInput(attrs={
            'autocomplete': 'current-password',
            'placeholder': 'Nhập mật khẩu hiện tại',
        }),
    )
    new_password1 = forms.CharField(
        label="Mật khẩu mới",
        strip=False,
        widget=forms.PasswordInput(attrs={
            'autocomplete': 'new-password',
            'placeholder': 'Nhập mật khẩu mới',
        }),
    )
    new_password2 = forms.CharField(
        label="Xác nhận mật khẩu mới",
        strip=False,
        widget=forms.PasswordInput(attrs={
            'autocomplete': 'new-password',
            'placeholder': 'Nhập lại mật khẩu mới',
        }),
    )


class ProductForm(forms.ModelForm):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    class Meta:
        model = Product
        fields = [
            'name',
            'category',
            'unit',
            'alert_threshold',
            'price_sell',
        ]

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get('name')
        unit = cleaned_data.get('unit')
        category = cleaned_data.get('category')
        alert_threshold = cleaned_data.get('alert_threshold')
        price_sell = cleaned_data.get('price_sell')

        if not (category or '').strip():
            self.add_error('category', "Danh mục là bắt buộc.")

        if alert_threshold is None:
            self.add_error('alert_threshold', "Ngưỡng cảnh báo tồn kho là bắt buộc.")

        if price_sell is None or price_sell <= 0:
            self.add_error('price_sell', "Giá bán là bắt buộc và phải lớn hơn 0.")

        if name and unit:
            existing_product = Product.objects.filter(
                user=self.user,
                name__iexact=name.strip(),
                unit__iexact=unit.strip(),
                category__iexact=(category or '').strip()
            )
            if self.instance and self.instance.pk:
                existing_product = existing_product.exclude(pk=self.instance.pk)
            existing_product = existing_product.first()

            if existing_product:
                raise forms.ValidationError(
                    "Sản phẩm này đã tồn tại. Vui lòng dùng sản phẩm cũ hoặc vào nhập hàng."
                )

        return cleaned_data


class PurchaseForm(forms.ModelForm):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields['product'].queryset = Product.objects.filter(user=user, is_active=True).order_by('name')

    class Meta:
        model = Purchase
        fields = [
            'product',
            'date',
            'supplier_name',
            'quantity',
            'unit_price',
            'payment_method',
            'payment_due_date',
            'note',
        ]
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'payment_due_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        quantity = cleaned_data.get('quantity')
        unit_price = cleaned_data.get('unit_price')

        if quantity and quantity <= 0:
            raise forms.ValidationError("Số lượng phải > 0")

        if unit_price and unit_price < 0:
            raise forms.ValidationError("Giá nhập không hợp lệ")

        return cleaned_data


class SaleForm(forms.ModelForm):
    update_product_price = forms.BooleanField(
        required=False,
        label="Cập nhật giá này thành giá bán mặc định mới"
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields['product'].queryset = Product.objects.filter(user=user, is_active=True).order_by('name')

    class Meta:
        model = Sale
        fields = [
            'product',
            'date',
            'customer_name',
            'quantity',
            'unit_price',
            'payment_method',
            'payment_due_date',
            'note',
        ]
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'payment_due_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        product = cleaned_data.get('product')
        quantity = cleaned_data.get('quantity')

        if product and quantity:
            available_stock = product.stock_quantity
            if self.instance and self.instance.pk and self.instance.product_id == product.id:
                available_stock += self.instance.quantity
            if quantity > available_stock:
                raise forms.ValidationError("Không đủ tồn kho để bán")

        return cleaned_data


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = [
            'date',
            'expense_type',
            'amount',
            'estimated_lifetime_months',
            'payment_method',
            'payment_due_date',
            'note',
        ]
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'estimated_lifetime_months': forms.NumberInput(attrs={
                'min': '1',
                'step': '1',
                'placeholder': 'Thời gian sử dụng (tháng)',
                'title': 'Số tháng dự kiến sử dụng hoặc hưởng lợi từ chi phí. Để trống nếu muốn tính toàn bộ vào kỳ phát sinh.',
            }),
            'payment_due_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        amount = cleaned_data.get('amount')

        if amount and amount <= 0:
            raise forms.ValidationError("Số tiền phải > 0")
        lifetime = cleaned_data.get('estimated_lifetime_months')
        if lifetime is not None and lifetime <= 0:
            raise forms.ValidationError("Thời gian sử dụng phải lớn hơn 0 tháng.")
        if cleaned_data.get('expense_type') == Expense.EXPENSE_TYPE_EQUIPMENT and not lifetime:
            raise forms.ValidationError("Nhập vòng đời của thiết bị theo số tháng.")

        return cleaned_data
