from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Expense, OpeningStock, Product, Purchase
from .utils import generate_prefix, remove_vietnamese
from .views import recognized_expense_summary


class ProductSkuTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="secret")

    def test_vietnamese_prefixes(self):
        self.assertEqual(remove_vietnamese("Điện tử"), "Dien tu")
        self.assertEqual(generate_prefix("Cà phê"), "CF")
        self.assertEqual(generate_prefix("Văn phòng phẩm"), "VP")
        self.assertEqual(generate_prefix("Phụ kiện máy"), "PKM")

    def test_product_generates_sequential_sku_from_level_one_category(self):
        first = Product.objects.create(
            user=self.user,
            name="Cà phê sữa",
            category="Cà phê / Nóng",
            unit="ly",
        )
        second = Product.objects.create(
            user=self.user,
            name="Cà phê đá",
            category="Cà phê > Lạnh",
            unit="ly",
        )

        self.assertEqual(first.sku, "CF-001")
        self.assertEqual(second.sku, "CF-002")

    def test_sku_sequence_is_scoped_to_user(self):
        other_user = User.objects.create_user(username="other", password="secret")
        first = Product.objects.create(
            user=self.user,
            name="Nước cam",
            category="Thức uống",
            unit="chai",
        )
        other = Product.objects.create(
            user=other_user,
            name="Nước táo",
            category="Thức uống",
            unit="chai",
        )

        self.assertEqual(first.sku, "TH-001")
        self.assertEqual(other.sku, "TH-001")

    def test_preview_api_returns_next_sku_without_creating_product(self):
        Product.objects.create(
            user=self.user,
            name="Bánh quy",
            category="Bánh kẹo",
            unit="hộp",
        )
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("preview_product_sku"),
            {"category": "Bánh kẹo / Bánh"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"sku": "BK-002"})
        self.assertEqual(Product.objects.count(), 1)


class InventorySummaryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="inventory-owner", password="secret")
        self.client.force_login(self.user)

    def test_inventory_summary_includes_opening_stock_and_purchases(self):
        opening_product = Product.objects.create(
            user=self.user,
            name="Sản phẩm có sẵn",
            category="Thực phẩm",
            unit="gói",
            price_sell=15000,
        )
        OpeningStock.objects.create(
            user=self.user,
            product=opening_product,
            quantity=4,
            estimated_unit_cost=5000,
        )
        purchased_product = Product.objects.create(
            user=self.user,
            name="Sản phẩm nhập thêm",
            category="Thực phẩm",
            unit="hộp",
            price_sell=30000,
        )
        Purchase.objects.create(
            user=self.user,
            product=purchased_product,
            date="2026-06-11",
            quantity=3,
            unit_price=12000,
        )

        response = self.client.get(reverse("inventory"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_stock"], 7)
        self.assertEqual(response.context["inventory_value"], 56000)
        self.assertNotContains(response, 'class="inventory-status-card inventory-status-card--setup"')

    def test_missing_stock_card_only_appears_for_product_without_stock_setup(self):
        Product.objects.create(
            user=self.user,
            name="Sản phẩm chưa nhập kho",
            category="Thực phẩm",
            unit="gói",
            price_sell=15000,
        )

        response = self.client.get(reverse("inventory"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="inventory-status-card inventory-status-card--setup"')
        self.assertContains(response, "Sản phẩm cần nhập hàng trước khi bán")


class ExpenseComparisonTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="expense-owner", password="secret")
        self.client.force_login(self.user)

    def test_report_comparison_includes_legacy_expense_for_sole_owner(self):
        Expense.objects.bulk_create([
            Expense(
                date=date(2026, 5, 20),
                expense_type="rent",
                amount=2000000,
            )
        ])
        Expense.objects.create(
            user=self.user,
            date=date(2026, 6, 10),
            expense_type="rent",
            amount=1000000,
        )

        response = self.client.get(
            reverse("report"),
            {"end_date": "2026-06-11", "expense_granularity": "month"},
        )

        rent_row = next(
            row for row in response.context["expense_comparison_rows"]
            if row["key"] == "rent"
        )
        self.assertEqual(rent_row["previous_total"], 2000000)
        self.assertGreater(rent_row["previous_width"], 0)
        self.assertEqual(rent_row["current_total"], 1000000)

    def test_legacy_expenses_are_not_shared_when_multiple_owners_exist(self):
        other_user = User.objects.create_user(username="other-expense-owner", password="secret")
        Expense.objects.bulk_create([
            Expense(
                date=date(2026, 5, 20),
                expense_type="rent",
                amount=2000000,
            )
        ])
        Expense.objects.create(
            user=self.user,
            date=date(2026, 6, 10),
            expense_type="rent",
            amount=1000000,
        )
        Expense.objects.create(
            user=other_user,
            date=date(2026, 6, 10),
            expense_type="electricity",
            amount=500000,
        )

        summary = recognized_expense_summary(
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 31),
            user=self.user,
        )

        self.assertEqual(summary["total"], 0)

    def test_expense_insight_lists_all_new_cost_groups(self):
        Expense.objects.create(
            user=self.user,
            date=date(2026, 5, 20),
            expense_type="rent",
            amount=1000000,
        )
        Expense.objects.create(
            user=self.user,
            date=date(2026, 6, 10),
            expense_type="rent",
            amount=300000,
        )
        Expense.objects.create(
            user=self.user,
            date=date(2026, 6, 10),
            expense_type="electricity",
            amount=400000,
        )
        Expense.objects.create(
            user=self.user,
            date=date(2026, 6, 10),
            expense_type="water",
            amount=300000,
        )

        response = self.client.get(
            reverse("report"),
            {"end_date": "2026-06-11", "expense_granularity": "month"},
        )

        insight = response.context["expense_insight"]
        self.assertIn("Các nhóm chi phí mới phát sinh kỳ này", insight)
        self.assertIn("Tiền điện (400.000 đ)", insight)
        self.assertIn("Tiền nước (300.000 đ)", insight)


class AccountSettingsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="settings-owner",
            email="owner@example.com",
            password="CurrentPass123!",
        )
        self.client.force_login(self.user)

    def test_settings_page_shows_username_without_exposing_password(self):
        response = self.client.get(reverse("account_settings"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "settings-owner")
        self.assertContains(response, "Mật khẩu được mã hóa một chiều")
        self.assertNotContains(response, "CurrentPass123!")

    def test_user_can_change_password_and_remain_logged_in(self):
        response = self.client.post(reverse("account_settings"), {
            "action": "change_password",
            "old_password": "CurrentPass123!",
            "new_password1": "NewSecurePass456!",
            "new_password2": "NewSecurePass456!",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mật khẩu đã được cập nhật thành công")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewSecurePass456!"))
        self.assertEqual(
            self.client.get(reverse("account_settings")).status_code,
            200,
        )

    def test_user_can_update_owner_name_and_topbar_context(self):
        response = self.client.post(reverse("account_settings"), {
            "action": "update_profile",
            "owner_name": "Nguyen Minh Anh",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nguyen Minh Anh")
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Nguyen Minh Anh")

        dashboard_response = self.client.get(reverse("dashboard"))
        self.assertEqual(
            dashboard_response.context["owner_name"],
            "Nguyen Minh Anh",
        )

    def test_owner_name_cannot_be_blank(self):
        response = self.client.post(reverse("account_settings"), {
            "action": "update_profile",
            "owner_name": "   ",
        })

        self.assertContains(response, "Vui lòng nhập tên chủ doanh nghiệp.")
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "")
