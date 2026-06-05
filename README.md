# Pixiu Flow

Pixiu Flow là một web app Django dành cho cửa hàng nhỏ để quản lý sản phẩm, tồn kho, bán hàng, nhập kho, chi phí, công nợ, dòng tiền và phân tích lợi nhuận. Sản phẩm được viết theo hướng dễ hiểu cho người không rành tài chính: giao diện tách rõ “lãi/lỗ ghi nhận” và “dòng tiền thật”, dùng nhãn tiếng Việt, tooltip giải thích công thức và các cảnh báo thao tác quan trọng.

## Mục Tiêu Sản Phẩm

Pixiu Flow giúp chủ cửa hàng trả lời nhanh các câu hỏi:

- Hôm nay/tháng này doanh thu bao nhiêu?
- Giá vốn hàng đã bán là bao nhiêu?
- Lợi nhuận gộp và lợi nhuận thuần đang thế nào?
- Tiền thật đã thu, đã chi và dòng tiền thuần là bao nhiêu?
- Sản phẩm nào sắp hết hàng, hết hàng hoặc chưa khai báo tồn kho?
- Khách nào còn nợ, nhà cung cấp/khoản chi nào sắp đến hạn thanh toán?
- Danh mục hoặc sản phẩm nào tạo doanh thu/lợi nhuận tốt nhất?
- Chi phí đang phát sinh theo nhóm nào và theo thời gian ra sao?

## Stack Kỹ Thuật

- Backend: Python, Django 5.2
- Database mặc định: SQLite (`db.sqlite3`)
- Auth: Django built-in User/Auth
- Frontend: Django templates, CSS thuần, JavaScript thuần
- Static serving: Django static files, WhiteNoise khi production
- Charts: phần lớn render bằng SVG/HTML/CSS inline để kiểm soát interaction và tránh phụ thuộc nặng vào Chart.js
- Ngôn ngữ giao diện: tiếng Việt
- Timezone: `Asia/Ho_Chi_Minh`

## Cách Chạy Local

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Mở app tại:

```text
http://127.0.0.1:8000/
```

Kiểm tra nhanh project:

```bash
python manage.py check
```

## Cấu Trúc Thư Mục

```text
config/
  settings.py              # Cấu hình Django, database, auth, static, timezone
  urls.py                  # Admin, core URLs, auth URLs
  wsgi.py / asgi.py

core/
  models.py                # Product, Category, OpeningStock, Purchase, Sale, Expense
  forms.py                 # Form cho sản phẩm, bán hàng, nhập hàng, chi phí
  views.py                 # Logic nghiệp vụ và render toàn bộ màn hình chính
  urls.py                  # Routes của app core
  admin.py                 # Django admin registration
  context_processors.py    # Business profile dùng trong layout
  templatetags/
    format_utils.py        # Format tiền VND và helper hiển thị
  templates/core/
    base.html
    landing.html
    login.html
    signup.html
    dashboard.html
    inventory.html
    setup_products.html
    sale_form.html
    expense_form.html
    bulk_transaction_form.html
    transaction_history.html
    report.html
  static/core/css/
    base.css
    sidebar.css
    dashboard.css
    inventory.css
    transactions.css
    analytics.css
    onboarding.css
    landing.css
    login.css
    signup.css
  static/core/js/
    inventory.js
    chart.js
```

## Data Model Chính

### User Scope

Các model nghiệp vụ kế thừa `TimeStampedModel`, gồm:

- `user = ForeignKey(User, null=True)`
- `created_at`
- `updated_at`

Dữ liệu cũ có thể có `user = null`. Dữ liệu mới nên gắn với `request.user`. Các view dùng helper `for_user(model, user)` để lọc dữ liệu theo user hiện tại.

### Product

Đại diện sản phẩm trong kho.

Trường quan trọng:

- `name`: tên sản phẩm
- `category`: đường dẫn danh mục dạng `Cấp 1 / Cấp 2 / ...`
- `unit`: đơn vị tính do user nhập, ví dụ `gói`, `cái`, `ly`
- `alert_threshold`: ngưỡng cảnh báo tồn kho
- `price_sell`: giá bán mặc định
- `price_buy_latest`: giá vốn/giá nhập gần nhất
- `supplier_name`: nhà cung cấp gần nhất
- `stock_quantity`: số tồn kho hiện tại
- `is_active`: trạng thái hoạt động

Logic tồn kho:

- `stock_status` phân loại: chưa khai báo tồn kho, hết hàng, sắp hết, đầy đủ.
- `has_imported` kiểm tra sản phẩm đã có `Purchase` hoặc `OpeningStock`.

### Category

Lưu danh mục dạng path. Hỗ trợ nhiều cấp bằng chuỗi:

```text
Đồ ăn / Đồ ăn khô / Mỳ
```

`unique_together = ('user', 'path')` để mỗi user có cây danh mục riêng.

### OpeningStock

Hàng ban đầu là số hàng cửa hàng đã có trước khi bắt đầu dùng Pixiu Flow.

Quan trọng:

- Không tạo dòng tiền ra.
- Không phải giao dịch mua hàng mới.
- Vẫn có `estimated_unit_cost` để hệ thống có giá vốn khi tính COGS/lợi nhuận gộp lúc bán.
- Khi lưu/xóa OpeningStock, hệ thống cập nhật lại `Product.stock_quantity`.

### Purchase

Giao dịch nhập kho mới.

Quan trọng:

- Tăng tồn kho.
- Cập nhật `price_buy_latest`.
- Có `payment_method`, `payment_due_date`, `payment_date` để theo dõi tiền đã chi hoặc công nợ.
- `total_amount = quantity * unit_price`.
- Trong accrual accounting, Purchase là nhập kho/tài sản, không được tính ngay là chi phí lãi/lỗ.
- Trong cash flow, Purchase đã thanh toán là tiền thực chi.

### Sale

Giao dịch bán hàng.

Quan trọng:

- Giảm tồn kho.
- `total_amount = quantity * unit_price`.
- Có `cogs_amount`: giá vốn tại thời điểm bán.
- Khi tạo Sale mới, nếu `cogs_amount` chưa có, hệ thống lấy `product.price_buy_latest * quantity`.
- COGS chỉ ghi nhận khi bán hàng, không ghi nhận khi nhập kho.
- Có thanh toán ngay hoặc nợ/chưa thanh toán.

### Expense

Chi phí vận hành và chi phí thiết bị.

Nhóm chính:

- Tiền điện
- Tiền nước
- Tiền mặt bằng
- Lương
- Vận chuyển
- Mua thiết bị
- Khác

Nếu là `Mua thiết bị`, cần `estimated_lifetime_months` để phân bổ/khấu hao trong báo cáo lãi/lỗ. Expense đã thanh toán cũng đi vào cash flow là tiền thực chi.

## Nguyên Tắc Tài Chính Trong App

Pixiu Flow tách 2 góc nhìn:

### 1. Lãi/Lỗ Ghi Nhận

Dựa trên accrual accounting:

```text
Doanh thu ghi nhận = tổng Sale trong kỳ, kể cả khách chưa trả tiền
Giá vốn hàng bán = tổng Sale.cogs_amount trong kỳ
Lợi nhuận gộp = Doanh thu ghi nhận - Giá vốn hàng bán
Chi phí vận hành = Expense được ghi nhận trong kỳ, có xử lý khấu hao thiết bị
Lợi nhuận thuần = Lợi nhuận gộp - Chi phí vận hành
```

Purchase không được cộng thẳng vào chi phí lãi/lỗ, vì nhập hàng là chuyển tiền thành tồn kho. Hàng chỉ thành giá vốn khi bán.

### 2. Dòng Tiền

Dựa trên cash basis:

```text
Tiền thực thu = Sale đã thanh toán
Tiền thực chi = Purchase/Expense đã thanh toán
Dòng tiền thuần = Tiền thực thu - Tiền thực chi
```

Khách nợ hoặc khoản chưa thanh toán không đi vào dòng tiền cho đến khi được đánh dấu đã thanh toán.

## Helper Tính Toán Quan Trọng

Trong `core/views.py`:

- `recognized_expense_summary(start_date, end_date, user)`: tính chi phí vận hành ghi nhận, gồm phân bổ thiết bị theo tháng.
- `cogs_summary(start_date, end_date, user)`: tính giá vốn hàng bán từ `Sale.cogs_amount`.
- `cash_flow_summary(start_date, end_date, user)`: tính tiền thực thu/thực chi theo ngày thanh toán.
- `build_payment_alerts(warning_days, limit, user)`: gom cảnh báo khách chưa thanh toán và khoản cần trả.
- `transaction_payment_status(...)`: trả trạng thái paid/unpaid/overdue/due today.

## Routes Chính

```text
/                              Landing page
/login/                        Login page custom
/signup/                       Signup page custom
/accounts/login/               Django auth login dùng template core/login.html
/accounts/logout/              Logout
/accounts/register/            Redirect về signup

/onboarding/                   Màn onboarding sau đăng ký
/onboarding/opening-stock/     Wizard cũ cho tồn kho ban đầu
/setup/products/               Màn khai báo/xem/sửa hàng ban đầu

/dashboard/                    Bảng theo dõi
/inventory/                    Sản phẩm & tồn kho
/products/create/              Thêm sản phẩm
/products/delete/<pk>/         Xóa sản phẩm

/sales/create/                 Ghi nhận bán hàng
/sales/create/ajax-new-product/ Thêm sản phẩm mới trong flow bán hàng

/expenses/create/              Ghi nhận nhập kho hoặc chi phí khác
/expenses/create/ajax-new-product/ Thêm sản phẩm mới trong flow nhập kho

/transactions/create/          Entry tạo giao dịch lẻ
/transactions/bulk-create/     Ghi nhận nhiều giao dịch
/transactions/history/         Lịch sử giao dịch
/transactions/<kind>/<pk>/mark-paid/   Đánh dấu đã thanh toán
/transactions/<kind>/<pk>/extend-due/  Đổi hạn thanh toán

/report/                       Phân tích thêm
```

## Các Page Và Nội Dung Hiện Có

### Landing

File:

- `core/templates/core/landing.html`
- `core/static/core/css/landing.css`

Vai trò:

- Giới thiệu Pixiu Flow.
- Dẫn user sang đăng ký/đăng nhập.
- Dùng hình Pixiu/logo và màu thương hiệu đỏ đậm/vàng.

### Login / Signup

Files:

- `core/templates/core/login.html`
- `core/templates/core/signup.html`
- `core/static/core/css/login.css`
- `core/static/core/css/signup.css`

Vai trò:

- Đăng nhập/đăng ký với giao diện custom đã có CSS.
- Signup lưu profile cơ bản vào session, tạo user, login luôn và đi vào onboarding/setup.

### Onboarding Và Thiết Lập Hàng Ban Đầu

Files:

- `core/templates/core/setup_products.html`
- `core/static/core/css/onboarding.css`

Vai trò:

- Dành cho số hàng đã có trước khi dùng Pixiu Flow.
- Không tạo Purchase, không tạo dòng tiền ra.
- Có thể khai báo sản phẩm, danh mục, đơn vị, giá bán, giá vốn ước tính, tồn kho ban đầu và ngưỡng cảnh báo.
- Nếu user đã khai báo trước đó, màn hình có thể load lại OpeningStock để xem/sửa.
- Nếu đã có giao dịch sau thiết lập, các thao tác sửa/xóa/thêm hàng ban đầu cần cảnh báo mạnh vì có thể làm lệch tồn kho và báo cáo.

UX hiện có:

- Bảng nhập nhiều dòng.
- Số thứ tự dòng.
- Placeholder cho các ô mẫu, không dùng text thật nếu user chưa nhập.
- Có nút thêm dòng/xóa dòng.
- Danh mục hỗ trợ thêm/xóa cấp dưới bằng nút `+`/`-`.
- Tooltip dạng icon `?` màu vàng/nâu, hiển thị popup gần icon.
- Hỗ trợ di chuyển giữa ô bằng bàn phím: mũi tên, Enter, Shift+Enter, Tab.

### Dashboard - Bảng Theo Dõi

Files:

- `core/templates/core/dashboard.html`
- `core/static/core/css/dashboard.css`

Vai trò:

- Màn hình tổng quan hằng ngày cho chủ cửa hàng.

Nội dung chính:

- Header có tên trang, profile chủ doanh nghiệp, chuông cảnh báo.
- Card nhắc thiết lập tồn kho nếu có sản phẩm chưa khai báo tồn kho.
- Card cảnh báo chưa thanh toán cho khách/NCC.
- Filter thời gian: tất cả, hôm nay, 7 ngày, tháng này, năm nay, date range.
- KPI được chia storytelling:
  - Row lãi/lỗ: doanh thu, lợi nhuận gộp, lợi nhuận thuần.
  - Row cash flow: tiền đã thu, tiền đã chi, dòng tiền thuần.
- Biểu đồ/tóm tắt theo kỳ.
- Các block nhắc việc và giao dịch gần đây.

Design:

- Card nền kem, border vàng/cam.
- CTA đỏ đậm.
- KPI dùng số lớn, nhưng đã giảm size để fit layout.
- Sidebar có option collapse/hide để tăng không gian màn hình chính.

### Inventory - Sản Phẩm & Tồn Kho

Files:

- `core/templates/core/inventory.html`
- `core/static/core/css/inventory.css`
- `core/static/core/js/inventory.js`

Vai trò:

- Quản lý sản phẩm, tồn kho, danh mục, nhà cung cấp, lô hàng và thiết lập ban đầu.

Nội dung chính:

- Search bar theo sản phẩm/danh mục/nhà cung cấp.
- Header CTA:
  - Nhập kho
  - Thêm sản phẩm
- Không đặt “Khai báo hàng ban đầu” ở header; chức năng này nằm trong panel thiết lập ban đầu.
- KPI tồn kho: chưa có tồn kho, hết hàng, sắp hết, số sản phẩm, giá trị tồn kho.
- Bảng sản phẩm:
  - Tên, mã, danh mục, tồn kho, ngưỡng, giá vốn, giá bán, margin, trạng thái, thanh toán, hành động.
  - Sort/filter.
  - Edit sản phẩm bằng popup ngay trong trang, không redirect về trang thêm sản phẩm.
- Popup edit sản phẩm:
  - Sửa tên, danh mục, đơn vị, nhà cung cấp, giá bán, ngưỡng cảnh báo.
  - Giá vốn chỉ cho sửa nếu sản phẩm chưa phát sinh Purchase. Nếu đã có nhập kho, phải sửa ở lịch sử giao dịch nhập kho.
  - Danh mục hiển thị dạng cây để dễ hiểu.
- Tab danh mục:
  - Cây danh mục nhiều cấp.
  - Thêm/sửa/xóa danh mục.
  - Bulk move sản phẩm.
- Panel bên phải:
  - Tóm tắt kho.
  - Cần xử lý.
  - Thiết lập ban đầu với trạng thái:
    - Chưa có OpeningStock: “Thiết lập hàng ban đầu”.
    - Đã có OpeningStock, chưa có giao dịch: “Xem / sửa hàng ban đầu”.
    - Đã có giao dịch: cảnh báo chỉ dùng OpeningStock cho hàng đã có trước khi dùng app.

### Product Form - Thêm Sản Phẩm

Files:

- `core/templates/core/product_form.html`
- `core/static/core/css/products.css`

Vai trò:

- Tạo hoặc sửa hồ sơ sản phẩm.
- Thêm sản phẩm mới không còn dùng “hàng có sẵn” như một giao dịch tùy tiện sau này.
- Nếu nhập kho khi tạo sản phẩm, tạo Purchase đúng nghĩa để ghi nhận tồn kho, công nợ/thanh toán và dòng tiền.
- Nếu chỉ tạo thông tin sản phẩm, chưa có tồn kho thì dashboard/inventory có thể nhắc cập nhật tồn kho.

### Sale Form - Ghi Nhận Doanh Thu

Files:

- `core/templates/core/sale_form.html`
- `core/static/core/css/transactions.css`

Vai trò:

- Ghi nhận bán hàng.
- Có thể bán nhiều dòng sản phẩm.
- Kiểm tra tồn kho trước khi lưu.
- Có thể thêm sản phẩm mới trong popup ngay trong flow bán hàng.
- Nếu thêm sản phẩm mới trong flow bán hàng thì phải khai báo tồn kho/giá vốn đủ để bán được.
- Thanh toán:
  - Tiền mặt
  - Chuyển khoản
  - Nợ/chưa thanh toán, có ngày nhắc nợ

### Expense/Purchase Form - Nhập Kho Và Chi Phí Khác

Files:

- `core/templates/core/expense_form.html`
- `core/static/core/css/transactions.css`

Vai trò:

- Cùng một màn xử lý 2 mode:
  - `mode=purchase`: nhập kho mới.
  - `mode=other`: chi phí khác.

Nhập kho:

- Chọn sản phẩm hoặc thêm sản phẩm mới bằng popup.
- Popup thêm sản phẩm mới có format giống popup thêm sản phẩm trong flow doanh thu, nhưng không có hộp nhập kho phụ bên dưới vì bản thân màn hiện tại đã là nhập kho.
- Danh mục trong popup hỗ trợ cấp 1-4, thêm/xóa cấp bằng UI.
- Lưu Purchase để tăng tồn kho, ghi giá vốn mới, công nợ/thanh toán và dòng tiền khi đã trả.

Chi phí khác:

- Chọn nhóm chi phí.
- Nếu là thiết bị, nhập vòng đời ước tính theo tháng.
- Có thể ghi nhận nợ/chưa thanh toán và ngày cần thanh toán.

### Bulk Transaction - Ghi Nhận Nhiều Giao Dịch

Files:

- `core/templates/core/bulk_transaction_form.html`
- `core/static/core/css/transactions.css`

Vai trò:

- Nhập nhiều giao dịch trong một bảng.
- Một dòng có thể đại diện cho một đơn hàng/phiếu nhập và có nhiều sản phẩm phụ cùng khách hàng/NCC.

Nội dung:

- Loại giao dịch: doanh thu, nhập hàng, chi phí.
- Ngày, sản phẩm/nhóm chi phí, khách hàng/NCC, giá trị, số lượng, thành tiền, thanh toán, ghi chú.
- Có nút thêm sản phẩm trong cùng dòng.
- Tổng giá trị cập nhật từ các dòng và sản phẩm phụ.
- Bảng có scroll, column co giãn, wrap nội dung để không che text.

### Transaction History - Lịch Sử Giao Dịch

Files:

- `core/templates/core/transaction_history.html`
- `core/static/core/css/history.css`

Vai trò:

- Nơi xem lại, lọc, sửa, xóa, đánh dấu thanh toán cho toàn bộ Sale/Purchase/Expense.

Nội dung:

- Filter thời gian.
- Search theo sản phẩm, mã SP, mã lô, đối tác, trạng thái thanh toán, số tiền.
- Filter theo loại, nội dung, đối tác, thanh toán, số lượng, giá trị.
- Sort theo cột.
- KPI tổng hợp lãi/lỗ và cash flow theo filter hiện tại.
- Action:
  - Sửa giao dịch.
  - Xóa giao dịch.
  - Đánh dấu đã thu/đã trả.
  - Đổi hạn thanh toán.
- Link từ các biểu đồ dòng tiền/report có thể đưa về trang này với filter thời gian đúng.

### Report - Phân Tích Thêm

Files:

- `core/templates/core/report.html`
- `core/static/core/css/analytics.css`

Vai trò:

- Phân tích sâu hơn dashboard.

Các section chính:

#### 1. Doanh Thu & Lợi Nhuận Gộp

KPI:

- Doanh thu
- Giá vốn
- Lợi nhuận gộp

Tab “Xu hướng theo thời gian”:

- Chart doanh thu và lợi nhuận gộp theo kỳ.
- Table: kỳ, doanh thu, giá vốn, lợi nhuận gộp, tăng trưởng doanh thu, tăng trưởng lợi nhuận gộp.

Tab “Đóng góp theo sản phẩm/danh mục”:

- Control bar:
  - Phân tích theo sản phẩm/danh mục.
  - Chỉ số doanh thu/lợi nhuận gộp.
  - Top 10/tất cả.
- Nếu chọn danh mục, có breadcrumb điều hướng cấp.
- Horizontal bar chart:
  - Ở cấp gốc hiển thị danh mục cấp 1.
  - Nếu click danh mục có con, hiển thị danh mục con trực tiếp.
  - Nếu không còn danh mục con, hiển thị sản phẩm trong danh mục đó.
- Bảng chi tiết: tên, số lượng bán, doanh thu, giá vốn, lợi nhuận gộp, tỷ trọng doanh thu, tỷ trọng lợi nhuận gộp.
- Filter nội bộ ưu tiên update section bằng JavaScript/fetch thay vì reload toàn trang.

#### 2. Phân Tích Dòng Tiền

- Group theo ngày/tuần/tháng/năm.
- Chart SVG tương tác:
  - Tiền thực thu ở nửa trên trục X.
  - Tiền thực chi ở nửa dưới trục X.
  - Dòng tiền thuần là line/marker theo kỳ, có vùng âm nếu dòng tiền âm.
- Tooltip dòng tiền chỉ hiển thị:
  - Tiền thực thu
  - Tiền thực chi
  - Dòng tiền thuần
- Click cột tiền vào/tiền ra sẽ mở detail panel.
- Detail panel không liệt kê từng giao dịch dài; có button “Xem chi tiết giao dịch” dẫn về lịch sử giao dịch với filter đúng kỳ.

#### 3. Phân Tích Chi Phí

- Column chart theo thời gian.
- User chọn gom theo ngày/tháng/năm.
- Data label nằm ngoài phía trên cột.
- Hover từng cột hiện box tooltip vuông, đi theo trỏ chuột, không có mũi tên.
- Tooltip có donut chart breakdown phần trăm chi phí trong kỳ đó.

#### 4. Phân Tích Biên Lợi Nhuận

Mục tiêu: đánh giá biên lợi nhuận gộp, không chỉ tổng lãi.

KPI:

- Biên lợi nhuận trung bình.
- Lãi trên mỗi đơn vị trung bình.
- Biên cao nhất.
- Biên thấp nhất.

Chart:

- Margin ranking dạng horizontal bar.
- Bar = biên lợi nhuận gộp %.
- Label phụ = lãi gộp trên đơn vị.
- Ghi chú phụ = số lượng bán.
- Tooltip khi hover bar: tên sản phẩm/danh mục, doanh thu, COGS, biên lợi nhuận.

Bảng chi tiết dạng cây:

- Vẫn giữ cấu trúc danh mục/sản phẩm với nút mở/thu gọn.
- Nếu filter theo sản phẩm, tự mở tất cả để thấy sản phẩm dưới danh mục.
- Cột: sản phẩm/danh mục, số lượng bán, giá bán TB, giá vốn TB, lãi gộp/đơn vị, biên lợi nhuận gộp, tổng lãi gộp, gợi ý.

Insight cards:

- Chỉ hiện khi đủ dữ liệu.
- Gợi ý theo logic:
  - Margin cao + quantity cao: sản phẩm chủ lực.
  - Margin cao + quantity thấp: có tiềm năng đẩy bán.
  - Margin thấp + quantity cao: bán tốt nhưng lãi mỏng.
  - Margin thấp + quantity thấp: cần xem lại.
  - Gross profit âm: đang lỗ.
- Text dùng đúng đơn vị user nhập, ví dụ `7 gói`, không dùng “đơn vị” chung chung.

#### 5. Tồn Kho Và Ranking

- Theo dõi giá trị tồn kho, sản phẩm chậm, tồn kho ngày cover.
- Ranking top product, supplier, dòng tiền, category/profit tùy dữ liệu.

## Design System Hiện Tại

### Nhận Diện

- Brand: Pixiu Flow.
- Visual mascot: hình Pixiu trong `core/static/core/images/`.
- Tone: thân thiện, thực dụng, dành cho chủ cửa hàng nhỏ.

### Màu Sắc

- Đỏ rượu/đỏ đậm: CTA chính, sidebar, heading quan trọng.
- Vàng/kem: nền app, card, filter bar.
- Xanh lá: giá trị tốt, lợi nhuận, cash in.
- Đỏ/cam: chi phí, cash out, cảnh báo.
- Xanh dương: doanh thu/dòng tiền thuần hoặc marker chart.

### Layout

- App shell dùng `base.html` với sidebar trái và topbar.
- Sidebar có collapse/hide để tăng không gian cho bảng lớn.
- Các page nghiệp vụ thường dùng:
  - Header page.
  - Filter/action bar.
  - Card KPI.
  - Table hoặc chart.
  - Right panel khi cần tóm tắt/cảnh báo.

### UI Pattern

- Button chính: nền đỏ đậm, text trắng/vàng.
- Button phụ: viền đỏ/vàng, nền kem.
- Card: border vàng/cam, radius vừa phải, nền kem nhạt.
- Tooltip:
  - Icon dấu hỏi trong vòng tròn.
  - Popup ngắn, gần icon hoặc con trỏ.
  - Dùng cho giải thích công thức/chú thích cột.
- Table:
  - Header nền vàng nhạt.
  - Có sort/filter icon.
  - Dữ liệu nhiều dùng scroll ngang/dọc.
  - Nội dung được wrap/co giãn để không bị che.

## Quy Ước Code

- View logic hiện tập trung trong `core/views.py`. File này lớn và chứa nhiều helper nội bộ.
- Khi tạo object mới, cần gắn `user=request.user`.
- Khi query dữ liệu nghiệp vụ, ưu tiên dùng `for_user(Model, request.user)`.
- Không tính Purchase như chi phí lãi/lỗ.
- Không phân bổ chi phí vận hành xuống từng danh mục/sản phẩm nếu không có logic quản trị rõ ràng; phần danh mục ưu tiên gross profit.
- OpeningStock chỉ dùng cho hàng đã có trước khi dùng app.
- Hàng mua thêm sau này phải dùng Purchase/“Nhập kho”.

## Các Luồng Nghiệp Vụ Quan Trọng

### Luồng User Mới

1. User đăng ký.
2. Đi qua onboarding/setup.
3. Có thể:
   - Khai báo hàng ban đầu nếu cửa hàng đã có hàng.
   - Bỏ qua để vào dashboard.
4. Sau đó quản lý qua dashboard, inventory, sale/purchase/expense.

### Luồng Hàng Ban Đầu

1. User vào `/setup/products/`.
2. Nếu chưa có OpeningStock, hiển thị bảng nhập mẫu.
3. Nếu đã có OpeningStock, load lại dữ liệu đã nhập để xem/sửa.
4. Nếu chưa có giao dịch, cho sửa/xóa/thêm bình thường.
5. Nếu đã có giao dịch, cảnh báo trước khi sửa vì có thể ảnh hưởng tồn kho và báo cáo.

### Luồng Nhập Kho Mới

1. User vào `/expenses/create/?mode=purchase`.
2. Chọn sản phẩm hoặc thêm sản phẩm mới.
3. Nhập số lượng, giá vốn, NCC, thanh toán.
4. Lưu Purchase.
5. Hệ thống tăng tồn kho, cập nhật giá vốn gần nhất và ghi nhận cash out nếu đã thanh toán.

### Luồng Bán Hàng

1. User vào `/sales/create/`.
2. Chọn sản phẩm, số lượng, giá bán, khách hàng.
3. Hệ thống kiểm tra tồn kho.
4. Lưu Sale.
5. Hệ thống giảm tồn kho và lưu COGS tại thời điểm bán.
6. Nếu thanh toán ngay, cash in được ghi nhận; nếu nợ, tạo cảnh báo công nợ.

### Luồng Công Nợ

1. Sale/Purchase/Expense có payment method `debt`.
2. User chọn ngày nhắc nợ/ngày cần thanh toán.
3. Dashboard/inventory/history hiển thị cảnh báo quá hạn/sắp hạn.
4. User có thể mark paid hoặc extend due date.

## Static Và CSS

CSS được chia theo page để dễ tìm:

- `base.css`: nền tảng layout chung.
- `sidebar.css`: sidebar và navigation.
- `dashboard.css`: dashboard.
- `inventory.css`: sản phẩm/tồn kho, modal edit sản phẩm.
- `transactions.css`: form bán hàng, nhập hàng, bulk transaction.
- `analytics.css`: trang report và chart tương tác.
- `onboarding.css`: setup hàng ban đầu.
- `landing.css`, `login.css`, `signup.css`: public/auth pages.
- `responsive.css`: responsive overrides.

Nếu sửa UI một page cụ thể, nên bắt đầu từ CSS cùng tên page.

## Static Assets

Ảnh nằm ở:

```text
core/static/core/images/
```

Gồm logo Pixiu, mascot Pixiu và một số SVG minh họa cho landing/feature.

## Deployment Notes

Project có:

- `Procfile`
- `gunicorn`
- `dj-database-url`
- `psycopg2-binary`
- `whitenoise`

Production nên set env:

```text
SECRET_KEY=...
DEBUG=False
ALLOWED_HOSTS=your-domain.com
CSRF_TRUSTED_ORIGINS=https://your-domain.com
DATABASE_URL=...
```

Collect static:

```bash
python manage.py collectstatic
```

## Những Điểm Cần Cẩn Thận Khi Phát Triển Tiếp

- `core/views.py` rất lớn; khi sửa nên tìm đúng helper/view trước bằng `rg`.
- Đừng thay đổi `cash_flow_summary()` nếu chỉ sửa lãi/lỗ, vì cash basis đang tách riêng.
- Đừng đưa Purchase vào chi phí accrual.
- Khi sửa giá vốn sản phẩm:
  - Nếu đã có Purchase, không sửa trực tiếp `price_buy_latest` trong popup sản phẩm.
  - Hướng user sửa giao dịch nhập kho ở lịch sử giao dịch.
- Khi sửa OpeningStock sau khi đã có giao dịch, phải cảnh báo user.
- Khi thêm page/template mới, đảm bảo dùng base/sidebar/topbar hiện có để không bị trang chỉ có HTML không CSS.
- Với chart trong report, nhiều chart được render bằng JS inline trong `report.html`; kiểm tra console nếu chart trắng.

## Lệnh Hữu Ích

```bash
# kiểm tra Django
python manage.py check

# chạy server
python manage.py runserver

# tạo migration
python manage.py makemigrations

# chạy migration
python manage.py migrate

# collect static production
python manage.py collectstatic
```

## Tóm Tắt Cho Người Mới Vào Codebase

Nếu cần hiểu nhanh:

1. Đọc `core/models.py` để hiểu data model.
2. Đọc phần helper đầu `core/views.py` để hiểu accounting/cash flow.
3. Đọc route trong `core/urls.py` để biết màn hình nào gọi view nào.
4. Mở template tương ứng trong `core/templates/core/`.
5. Sửa CSS trong file theo module ở `core/static/core/css/`.
6. Sau mỗi thay đổi, chạy `python manage.py check` và mở page trong browser.

Pixiu Flow hiện là app Django template-first, không phải SPA. Phần tương tác nâng cao nằm trong JavaScript ngay trong template hoặc file JS nhỏ, còn source of truth nghiệp vụ vẫn nằm ở Django models/views.
