# Pixiu Flow

Pixiu Flow là website quản lý tài chính, giao dịch và tồn kho cho chủ kinh doanh nhỏ. README này được viết để Claude/Codex hoặc một người mới vào dự án có thể đọc nhanh và hình dung được nội dung website, các trang đang có, logic dữ liệu, đường link và phong cách giao diện.

## Tổng Quan Sản Phẩm

Pixiu Flow giúp chủ shop nhỏ ghi nhận doanh thu, nhập hàng, chi phí, công nợ, tồn kho và xem báo cáo tài chính bằng tiếng Việt dễ hiểu. Sản phẩm không đi theo hướng phần mềm kế toán nặng nề; trọng tâm là workflow hằng ngày: bán gì, còn bao nhiêu hàng, khách nào chưa trả, khoản nào sắp đến hạn, doanh thu/lợi nhuận/dòng tiền ra sao.

Người dùng mục tiêu:
- Chủ cửa hàng nhỏ, shop online, quán ăn/uống, hộ kinh doanh.
- Freelancer hoặc cá nhân tự theo dõi thu chi.
- Người không chuyên kế toán nhưng cần dashboard rõ ràng để ra quyết định.

Tông giao diện:
- Ấm, thân thiện, nghiệp vụ, có nhận diện Pixiu/linh vật.
- Màu chủ đạo: đỏ đậm, vàng/kem, trắng; xanh/lục cho trạng thái tốt.
- Layout chính: sidebar trái, topbar, form/card nghiệp vụ, bảng dữ liệu, KPI và biểu đồ.

## Công Nghệ

- Django 5.2
- SQLite local qua `db.sqlite3`, production có thể dùng `DATABASE_URL`.
- Static files bằng Django static + WhiteNoise.
- Icon Lucide qua CDN trong `core/templates/core/base.html`.
- CSS nằm trong `core/static/core/css/`.
- Templates nằm trong `core/templates/core/`.

Chạy local:

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Kiểm tra:

```bash
python manage.py check
python manage.py test core
```

## Cấu Trúc Code

- `config/settings.py`: cấu hình Django, database, static, timezone.
- `core/urls.py`: map route chính.
- `core/models.py`: model nghiệp vụ.
- `core/views.py`: view, query KPI, lưu giao dịch, logic báo cáo/công nợ.
- `core/forms.py`: Django forms cho product/purchase/sale/expense.
- `core/templates/core/`: giao diện HTML.
- `core/static/core/css/`: style theo từng page.
- `core/templatetags/format_utils.py`: format tiền và helper hiển thị.

## Model Và Logic Dữ Liệu

Tất cả model nghiệp vụ kế thừa `TimeStampedModel`, có `user`, `created_at`, `updated_at`. Dữ liệu được tách theo tài khoản bằng helper `for_user(Model, request.user)`.

Model chính:
- `Product`: sản phẩm, SKU tự động, danh mục dạng path text, đơn vị, giá bán, giá vốn gần nhất, nhà cung cấp, tồn kho, ngưỡng cảnh báo, active/inactive.
- `Category`: danh mục dạng path tối đa 4 cấp.
- `OpeningStock`: tồn kho ban đầu.
- `Purchase`: nhập hàng, tăng tồn kho, cập nhật giá vốn gần nhất, có thể có công nợ nhà cung cấp.
- `Sale`: bán hàng/doanh thu, giảm tồn kho, lưu `total_amount`, lưu `cogs_amount` tại thời điểm bán, có thể có công nợ khách. Khách hàng chỉ là chuỗi `customer_name`, không có customer ID.
- `Expense`: chi phí khác, gồm điện/nước/mặt bằng/lương/vận chuyển/thiết bị/khác. Thiết bị có `estimated_lifetime_months` để phân bổ chi phí.

Thanh toán:
- `cash`: tiền mặt, xem như đã thanh toán.
- `transfer`: chuyển khoản, xem như đã thanh toán.
- `debt`: nợ/chưa thanh toán, cần `payment_due_date`.

Logic tài chính:
- Doanh thu ghi nhận lấy từ `Sale.total_amount`, kể cả khách chưa trả.
- Dòng tiền chỉ tính giao dịch đã thanh toán hoặc đã bấm đã thu/đã trả.
- Giá vốn hàng bán lấy từ `Sale.cogs_amount`, không tính lại bằng giá vốn hiện tại.
- Lợi nhuận gộp = doanh thu - giá vốn hàng bán.
- Lợi nhuận thuần = lợi nhuận gộp - chi phí vận hành.
- Nhập hàng ảnh hưởng tồn kho và dòng tiền, không đi thẳng vào chi phí lãi/lỗ cho tới khi hàng được bán.

## Navigation Và Link Chính

Sidebar trong `base.html`:
- `/` - Trang chủ/landing.
- `/dashboard/` - Bảng theo dõi.
- `/transactions/history/` - Lịch sử giao dịch.
- `/transactions/create/` - Ghi nhận giao dịch lẻ.
- `/transactions/bulk-create/` - Ghi nhận nhiều giao dịch.
- `/inventory/` - Sản phẩm & tồn kho.
- `/report/` - Xem thêm chỉ số.
- `/settings/` - Cài đặt tài khoản.

Route nghiệp vụ:
- `/sales/create/` - tạo doanh thu.
- `/expenses/create/` - tạo chi phí hoặc nhập hàng.
- `/expenses/create/?mode=purchase&product_id=<id>` - nhập hàng cho sản phẩm cụ thể.
- `/products/create/` - tạo/sửa sản phẩm.
- `/products/preview-sku/` - preview SKU.
- `/transactions/<kind>/<id>/mark-paid/` - đánh dấu đã thanh toán.
- `/transactions/<kind>/<id>/extend-due/` - đổi hạn thanh toán.

## Các Trang Chính

### Landing `/`

Template `landing.html`. Trang giới thiệu Pixiu Flow trước đăng nhập, dẫn tới login/signup.

### Login/Signup `/login/`, `/signup/`

Templates `login.html`, `signup.html`. Sau đăng nhập chuyển về dashboard.

### Onboarding Và Setup Sản Phẩm `/onboarding/`, `/setup/products/`

Giúp người dùng khai báo sản phẩm và tồn kho ban đầu. `setup_products.html` cho nhập nhiều sản phẩm với tên, danh mục, đơn vị, giá bán, tồn kho, giá vốn ước tính, ngưỡng cảnh báo. Nếu có tồn đầu kỳ thì tạo `OpeningStock`.

### Dashboard `/dashboard/`

Template `dashboard.html`, CSS `dashboard.css`. Đây là màn chính sau login.

Nội dung:
- Checklist bắt đầu nhanh.
- Cảnh báo sản phẩm thiếu tồn kho, hết hàng/sắp hết hàng.
- Cảnh báo công nợ khách/NCC/chi phí.
- Bộ lọc kỳ xem: tất cả, hôm nay, 7 ngày, tháng này, năm nay, custom date.
- KPI lãi/lỗ: doanh thu ghi nhận, lợi nhuận gộp, lợi nhuận thuần.
- KPI dòng tiền: tiền đã thu, tiền đã chi, dòng tiền thuần.
- Action Checklist panel “Cần làm” cạnh phải KPI khi có việc cần xử lý.
- Biểu đồ xu hướng và thống kê nhanh.

Action Checklist lấy toàn bộ trạng thái hiện tại của user, không filter theo ngày dashboard. Priority đỏ/cam/xanh dựa trên nợ quá hạn, sắp đến hạn, tồn kho, sản phẩm thiếu tồn và nhắc nhở định kỳ.

### Ghi Nhận Giao Dịch Lẻ `/transactions/create/`, `/sales/create/`, `/expenses/create/`

Templates `sale_form.html`, `expense_form.html`.

Doanh thu mới:
- Nhập khách hàng tùy chọn, ngày, nhiều dòng sản phẩm, đơn giá, số lượng, thanh toán, ngày nhắc thu nợ, ghi chú.
- Có autocomplete sản phẩm.
- Có thể tạo sản phẩm mới ngay trong form bán hàng bằng modal.
- Khi lưu `Sale`, tồn kho giảm.
- Field khách hàng là input text thường, click/focus hiện top 5 tên khách thường gặp từ lịch sử `Sale.customer_name`; gõ thì filter realtime, highlight phần khớp, chọn thì điền chuỗi vào input.

Chi phí mới:
- Mode nhập hàng tạo `Purchase`, tăng tồn kho, cập nhật giá vốn.
- Mode chi phí khác tạo `Expense`.
- Nếu nợ/chưa thanh toán thì cần ngày nhắc thanh toán.

### Ghi Nhận Nhiều Giao Dịch `/transactions/bulk-create/`

Template `bulk_transaction_form.html`. Màn nhập nhanh dạng bảng giống spreadsheet. Mỗi dòng có thể là doanh thu, nhập hàng hoặc chi phí. Có validate theo dòng, lưu hàng loạt và báo số dòng đã lưu.

### Lịch Sử Giao Dịch `/transactions/history/`

Template `transaction_history.html`. Gom `Sale`, `Purchase`, `Expense` thành một bảng chung.

Tính năng:
- Search theo mô tả, đối tác, mã, trạng thái, số tiền.
- Lọc theo loại, ngày, mô tả, đối tác, payment, số lượng, số tiền.
- Sort cột.
- Sửa/xóa giao dịch.
- Đánh dấu đã thu/đã trả, đổi hạn thanh toán.

### Inventory `/inventory/`

Template `inventory.html`. Trang quản lý sản phẩm, danh mục, tồn kho, nhà cung cấp, thiết bị và cảnh báo.

Nội dung:
- Tổng sản phẩm, tổng tồn, giá trị tồn, số cảnh báo.
- Danh sách sản phẩm theo trạng thái: chưa khai báo tồn, hết hàng, sắp hết, đầy đủ.
- Cây danh mục tối đa 4 cấp.
- Thống kê top bán chạy, nhà cung cấp, công nợ liên quan.
- Inline update sản phẩm và quản lý category.

### Product Form `/products/create/`

Template `product_form.html`. Tạo/sửa sản phẩm, preview SKU, validate chống trùng theo user/name/unit/category.

### Report `/report/`

Template `report.html`, CSS `analytics.css`. Trang phân tích sâu với tab:
- Doanh thu.
- Lợi nhuận.
- Chi phí.
- Dòng tiền.

Có date range toàn trang, chart/table theo granularity ngày/tuần/tháng/năm, phân tích sản phẩm/danh mục, công nợ, chi phí thiết bị và phân biệt dòng tiền với lãi/lỗ. Khi mở report, session set `report_viewed = True`.

### Settings `/settings/`

Template `account_settings.html`. Đổi mật khẩu và thông tin tài khoản/session.

## Design Notes Cho AI

Khi sửa UI:
- Giữ chất dashboard nghiệp vụ, không biến thành landing page.
- Ưu tiên layout gọn, dễ scan, thao tác nhanh.
- Dùng icon Lucide nếu thêm nút/action.
- Giữ palette đỏ đậm, kem/vàng, trắng, xanh trạng thái.
- Không thêm trang trí gradient/orb không liên quan.
- Text tiếng Việt nên trực tiếp, dễ hiểu cho chủ shop.

Khi sửa logic:
- Luôn lọc dữ liệu theo user bằng `for_user`.
- Nếu sửa `Sale`/`Purchase`/`OpeningStock`, nhớ tác động tồn kho.
- Nếu sửa payment/debt, kiểm tra dashboard alert, history action và transaction side.
- Nếu thêm model field, cần migration.
- Nếu sửa báo cáo, phân biệt rõ doanh thu ghi nhận/lợi nhuận và dòng tiền.

