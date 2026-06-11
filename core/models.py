from django.db import IntegrityError, models, transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth.models import User

class TimeStampedModel(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Product(TimeStampedModel):

    name = models.CharField(max_length=255)
    sku = models.CharField(
        max_length=20,
        blank=True,
        db_index=True,
        help_text="Mã sản phẩm tự động. Ví dụ: CF-001",
    )
    category = models.CharField(max_length=100, blank=True)
    unit = models.CharField(max_length=50)
    alert_threshold = models.PositiveIntegerField(default=10)

    price_sell = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    price_buy_latest = models.DecimalField(max_digits=12, decimal_places=0, default=0)

    supplier_name = models.CharField(max_length=255, blank=True)

    stock_quantity = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("user", "sku")]
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        should_generate_sku = not self.sku and self.user_id
        if not should_generate_sku:
            return super().save(*args, **kwargs)

        from core.utils import generate_product_sku

        for attempt in range(5):
            self.sku = generate_product_sku(self.user, self.category or "SP")
            try:
                with transaction.atomic():
                    return super().save(*args, **kwargs)
            except IntegrityError:
                self.sku = ""
                if attempt == 4:
                    raise

    @property
    def has_imported(self):
        return self.purchases.exists() or self.opening_stocks.exists()

    @property
    def stock_status(self):
        if self.stock_quantity <= 0 and not self.has_imported:
            return "chua_nhap_hang"
        if self.stock_quantity <= 0:
            return "het_hang"
        if self.stock_quantity <= self.alert_threshold:
            return "sap_het"
        return "day_du"

    @property
    def stock_status_label(self):
        mapping = {
            "chua_nhap_hang": "Chưa khai báo tồn kho",
            "het_hang": "Hết hàng",
            "sap_het": "Sắp hết",
            "day_du": "Đầy đủ",
        }
        return mapping.get(self.stock_status, "")


class Category(TimeStampedModel):
    path = models.CharField(max_length=255)
    name = models.CharField(max_length=100)
    note = models.TextField(blank=True)

    class Meta:
        unique_together = ('user', 'path')
        ordering = ['path']

    def __str__(self):
        return self.path


class Purchase(TimeStampedModel):
    PAYMENT_METHOD_CASH = 'cash'
    PAYMENT_METHOD_TRANSFER = 'transfer'
    PAYMENT_METHOD_DEBT = 'debt'
    PAYMENT_METHOD_CHOICES = (
        (PAYMENT_METHOD_CASH, 'Tiền mặt'),
        (PAYMENT_METHOD_TRANSFER, 'Chuyển khoản'),
        (PAYMENT_METHOD_DEBT, 'Nợ/chưa thanh toán'),
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='purchases'
    )
    date = models.DateField()

    supplier_name = models.CharField(max_length=255, blank=True)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default=PAYMENT_METHOD_CASH)
    payment_due_date = models.DateField(blank=True, null=True)
    payment_date = models.DateField(blank=True, null=True)

    note = models.TextField(blank=True)

    class Meta:
      
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"Nhập hàng - {self.product.name} - {self.date}"

    def clean(self):
        if self.quantity <= 0:
            raise ValidationError("Số lượng nhập phải lớn hơn 0.")
        if self.unit_price < 0:
            raise ValidationError("Đơn giá nhập không được âm.")

        if self.payment_method == self.PAYMENT_METHOD_DEBT and not self.payment_due_date:
            raise ValidationError("Nhập ngày cần thanh toán khi chọn nợ/chưa thanh toán.")

        if self.payment_due_date and self.payment_due_date < timezone.now().date():
            raise ValidationError("Ngay can thanh toan khong duoc som hon hom nay.")

    def save(self, *args, **kwargs):
        self.full_clean()
        if self.payment_method != self.PAYMENT_METHOD_DEBT:
            self.payment_due_date = None
            if not self.payment_date:
                self.payment_date = self.date
        else:
            self.payment_date = None
        self.total_amount = self.quantity * self.unit_price

        is_new = self.pk is None
        old_quantity = 0
        old_product = None

        if not is_new:
            old_obj = Purchase.objects.get(pk=self.pk)
            old_quantity = old_obj.quantity
            old_product = old_obj.product

        super().save(*args, **kwargs)

        if old_product and old_product.pk != self.product.pk:
            old_product.stock_quantity -= old_quantity
            old_product.save()
            stock_diff = self.quantity
        else:
            stock_diff = self.quantity - old_quantity

        self.product.stock_quantity += stock_diff
        self.product.price_buy_latest = self.unit_price

        if self.supplier_name:
            self.product.supplier_name = self.supplier_name

        self.product.save()

    def delete(self, *args, **kwargs):
        self.product.stock_quantity -= self.quantity
        self.product.save()
        super().delete(*args, **kwargs)


class OpeningStock(TimeStampedModel):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='opening_stocks'
    )
    quantity = models.PositiveIntegerField()
    estimated_unit_cost = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    stock_date = models.DateField(blank=True, null=True)
    note = models.TextField(blank=True)

    class Meta:
 
        ordering = ['-created_at']

    def __str__(self):
        return f"Ton kho khoi diem - {self.product.name}"

    def clean(self):
        if self.quantity <= 0:
            raise ValidationError("So luong ton kho khoi diem phai lon hon 0.")
        if self.estimated_unit_cost < 0:
            raise ValidationError("Gia von uoc tinh khong duoc am.")

    def save(self, *args, **kwargs):
        self.full_clean()
        is_new = self.pk is None
        old_quantity = 0

        if not is_new:
            old_obj = OpeningStock.objects.get(pk=self.pk)
            old_quantity = old_obj.quantity

        super().save(*args, **kwargs)

        self.product.stock_quantity += self.quantity - old_quantity
        if self.estimated_unit_cost:
            self.product.price_buy_latest = self.estimated_unit_cost
        self.product.save()

    def delete(self, *args, **kwargs):
        self.product.stock_quantity -= self.quantity
        self.product.save()
        super().delete(*args, **kwargs)


class Sale(TimeStampedModel):
    PAYMENT_METHOD_CASH = 'cash'
    PAYMENT_METHOD_TRANSFER = 'transfer'
    PAYMENT_METHOD_DEBT = 'debt'
    PAYMENT_METHOD_CHOICES = (
        (PAYMENT_METHOD_CASH, 'Tiền mặt'),
        (PAYMENT_METHOD_TRANSFER, 'Chuyển khoản'),
        (PAYMENT_METHOD_DEBT, 'Nợ/chưa thanh toán'),
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='sales'
    )
    date = models.DateField()

    customer_name = models.CharField(max_length=255, blank=True)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    cogs_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        help_text="Gia von tai thoi diem ban, tinh tu price_buy_latest cua san pham",
    )
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default=PAYMENT_METHOD_CASH)
    payment_due_date = models.DateField(blank=True, null=True)
    payment_date = models.DateField(blank=True, null=True)

    note = models.TextField(blank=True)
    
    class Meta:

        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"Bán hàng - {self.product.name} - {self.date}"

    def clean(self):
        if self.quantity <= 0:
            raise ValidationError("Số lượng bán phải lớn hơn 0.")
        if self.unit_price < 0:
            raise ValidationError("Đơn giá bán không được âm.")
        if self.payment_method == self.PAYMENT_METHOD_DEBT and not self.payment_due_date:
            raise ValidationError("Nhập ngày nhắc nợ khi chọn nợ/chưa thanh toán.")

        if self.payment_due_date and self.payment_due_date < timezone.now().date():
            raise ValidationError("Ngay nhac no khong duoc som hon hom nay.")

    def save(self, *args, **kwargs):
        self.full_clean()
        if self.payment_method != self.PAYMENT_METHOD_DEBT:
            self.payment_due_date = None
            if not self.payment_date:
                self.payment_date = self.date
        else:
            self.payment_date = None
        self.total_amount = self.quantity * self.unit_price
        if not self.cogs_amount and self.product_id:
            self.cogs_amount = (self.product.price_buy_latest or 0) * self.quantity

        is_new = self.pk is None
        old_quantity = 0
        old_product = None

        if not is_new:
            old_obj = Sale.objects.get(pk=self.pk)
            old_quantity = old_obj.quantity
            old_product = old_obj.product

        super().save(*args, **kwargs)

        if old_product and old_product.pk != self.product.pk:
            old_product.stock_quantity += old_quantity
            old_product.save()
            stock_diff = self.quantity
        else:
            stock_diff = self.quantity - old_quantity

        self.product.stock_quantity -= stock_diff
        self.product.save()

    def delete(self, *args, **kwargs):
        self.product.stock_quantity += self.quantity
        self.product.save()
        super().delete(*args, **kwargs)


class Expense(TimeStampedModel):
    PAYMENT_METHOD_CASH = 'cash'
    PAYMENT_METHOD_TRANSFER = 'transfer'
    PAYMENT_METHOD_DEBT = 'debt'
    EXPENSE_TYPE_EQUIPMENT = 'equipment'
    PAYMENT_METHOD_CHOICES = (
        (PAYMENT_METHOD_CASH, 'Tiền mặt'),
        (PAYMENT_METHOD_TRANSFER, 'Chuyển khoản'),
        (PAYMENT_METHOD_DEBT, 'Nợ/chưa thanh toán'),
    )

    EXPENSE_TYPE_CHOICES = (
        ('electricity', 'Tiền điện'),
        ('water', 'Tiền nước'),
        ('rent', 'Tiền mặt bằng'),
        ('salary', 'Lương'),
        ('transport', 'Vận chuyển'),
        (EXPENSE_TYPE_EQUIPMENT, 'Mua thiết bị'),
        ('other', 'Khác'),
    )

    date = models.DateField()
    expense_type = models.CharField(max_length=50, choices=EXPENSE_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=0)
    estimated_lifetime_months = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="Thời gian sử dụng (tháng)",
        help_text="Số tháng dự kiến sử dụng hoặc hưởng lợi từ chi phí. Để trống = tính toàn bộ vào kỳ phát sinh.",
    )
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default=PAYMENT_METHOD_CASH)
    payment_due_date = models.DateField(blank=True, null=True)
    payment_date = models.DateField(blank=True, null=True)
    note = models.TextField(blank=True)

    class Meta:
       
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.get_expense_type_display()} - {self.amount}"

    def clean(self):
        if self.amount <= 0:
            raise ValidationError("S? ti?n chi ph? ph?i l?n h?n 0.")
        if self.payment_method == self.PAYMENT_METHOD_DEBT and not self.payment_due_date:
            raise ValidationError("Nh?p ng?y c?n thanh to?n khi ch?n n?/ch?a thanh to?n.")

        if self.payment_due_date and self.payment_due_date < timezone.now().date():
            raise ValidationError("Ngay can thanh toan khong duoc som hon hom nay.")
        if self.estimated_lifetime_months is not None and self.estimated_lifetime_months <= 0:
            raise ValidationError("Thời gian sử dụng phải lớn hơn 0 tháng.")
        if self.expense_type == self.EXPENSE_TYPE_EQUIPMENT and not self.estimated_lifetime_months:
            raise ValidationError("Nhập vòng đời của thiết bị theo số tháng.")

    def save(self, *args, **kwargs):
        self.full_clean()
        if self.payment_method != self.PAYMENT_METHOD_DEBT:
            self.payment_due_date = None
            if not self.payment_date:
                self.payment_date = self.date
        else:
            self.payment_date = None
        super().save(*args, **kwargs)
