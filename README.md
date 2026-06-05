# Pixiu Flow - Quản lý tồn kho, giao dịch và phân tích tài chính

Pixiu Flow là một web app Django dành cho cửa hàng/doanh nghiệp nhỏ để ghi nhận bán hàng, nhập hàng, chi phí vận hành, theo dõi tồn kho, công nợ, dòng tiền và lãi/lỗ. Sản phẩm được thiết kế cho người dùng không có kiến thức kế toán sâu, nên giao diện ưu tiên các khái niệm dễ hiểu như "tiền vào", "tiền ra", "lợi nhuận ghi nhận", "cần thu/cần trả" và có tooltip giải thích cách tính.

## Công nghệ

- Backend: Python, Django 5.2.x
- Database mặc định: SQLite (`db.sqlite3`)
- Frontend: Django templates, CSS thuần, JavaScript thuần
- Chart: Chart.js cho một số biểu đồ canvas, kết hợp biểu đồ HTML/CSS ở các khu phân tích tùy biến
- Ngôn ngữ/timezone: tiếng Việt, `Asia/Ho_Chi_Minh`

## Cấu trúc chính

```text
config/
  settings.py              # Cấu hình Django, SQLite, static, locale
  urls.py                  # Include URL của core

core/
  models.py                # Product, Category, Purchase, Sale, Expense, OpeningStock
  forms.py                 # Form sản phẩm, bán hàng, nhập hàng, chi phí
  views.py                 # Toàn bộ logic màn hình, báo cáo, công nợ, cash flow
  urls.py                  # Route của app
  templatetags/
    format_utils.py        # Format VND, xử lý một số text hiển thị
  templates/core/          # HTML cho landing, dashboard, inventory, transactions, report
  static/core/css/         # CSS theo module
  static/core/js/          # JS inventory và chart
```

## Các màn hình đang có

### 1. Landing, đăng nhập, đăng ký, onboarding

- `/` - landing page giới thiệu Pixiu Flow.
- `/login/`, `/signup/` - giao diện đăng nhập/đăng ký.
- `/setup/products/` - thiết lập sản phẩm và hàng ban đầu.

### 2. Bảng theo dõi

Route: `/dashboard/`

Mục tiêu: hiển thị nhanh tình hình hoạt động trong một khoảng thời gian.

Đang có:

- Bộ lọc thời gian dùng chung cho toàn trang: `Tất cả`, `Hôm nay`, `7 ngày`, `Tháng này`, date range.
- KPI theo ghi nhận:
  - Doanh thu ghi nhận
  - Chi phí ghi nhận
  - Lợi nhuận ghi nhận
- KPI theo dòng tiền:
  - Tiền vào
  - Tiền ra
  - Dòng tiền thuần
- Tooltip giải thích từng KPI theo ngôn ngữ dễ hiểu.
- Cảnh báo chưa thanh toán:
  - Khách chưa thanh toán
  - Cần thanh toán cho nhà cung cấp/chi phí
  - Có ngưỡng cảnh báo trước hạn, mặc định 7 ngày, có thể chỉnh trong session.
  - Có nút nhanh xác nhận "Đã thanh toán hôm nay".
- Thống kê nhanh, biểu đồ xu hướng, cảnh báo tồn kho.

### 3. Sản phẩm và tồn kho

Route: `/inventory/`

Mục tiêu: quản lý danh sách sản phẩm, danh mục, nhà cung cấp, lô hàng và tình trạng tồn kho.

Đang có:

- Thanh tìm kiếm topbar có nút xóa nhanh.
- Bộ lọc nhanh trạng thái tồn kho:
  - Hết hàng
  - Sắp hết
  - Tổng sản phẩm
  - Giá trị tồn kho
- Bảng sản phẩm:
  - Tên, mã SP, đơn vị, ngày thêm, danh mục, tồn kho, ngưỡng, giá vốn, giá bán, margin, trạng thái, thanh toán, hành động.
  - Filter/sort theo nhiều cột.
  - Cột thanh toán có filter.
  - Inline edit ngưỡng cảnh báo tồn kho.
  - Action sửa/xóa/xem chi tiết.
- Tab danh mục:
  - Cây danh mục nhiều cấp.
  - Thêm/sửa/xóa danh mục.
  - Di chuyển sản phẩm giữa danh mục.
- Tab nhà cung cấp/lô hàng:
  - Xem nhà cung cấp.
  - Xem lô nhập.
  - Tìm kiếm/filter theo nhà cung cấp/lô hàng.
- Panel bên phải:
  - Tóm tắt kho.
  - Box "Cần xử lý" gom tồn kho sắp hết và cảnh báo thanh toán.
  - Bán chạy nhất.
  - Danh mục lợi nhuận cao.

### 4. Ghi nhận giao dịch lẻ

Route: `/transactions/create/`

Đây là entry chung, chuyển người dùng sang form phù hợp.

Các form cụ thể:

- `/sales/create/` - bán hàng/doanh thu.
- `/expenses/create/?mode=purchase` - nhập hàng.
- `/expenses/create/` - chi phí khác.

Đang có:

- Bán hàng:
  - Chọn sản phẩm, ngày, khách hàng, số lượng, đơn giá.
  - Kiểm tra không bán quá tồn kho.
  - Có tùy chọn cập nhật giá bán mặc định.
  - Hỗ trợ thanh toán ngay hoặc nợ/chưa thanh toán.
- Nhập hàng:
  - Chọn sản phẩm, ngày, nhà cung cấp, số lượng, đơn giá.
  - Tự cập nhật tồn kho, giá nhập mới nhất và nhà cung cấp của sản phẩm.
  - Hỗ trợ nợ nhà cung cấp.
- Chi phí khác:
  - Nhóm chi phí: tiền điện, nước, mặt bằng, lương, vận chuyển, mua thiết bị, khác.
  - Nếu chọn `Mua thiết bị`, yêu cầu nhập `estimated_lifetime_months` để tính khấu hao/phân bổ chi phí.
  - Nếu không phải mua thiết bị, không hiển thị vòng đời, chỉ dùng ghi chú.

### 5. Ghi nhận nhiều giao dịch

Route: `/transactions/bulk-create/`

Mục tiêu: nhập nhiều dòng doanh thu/nhập hàng/chi phí cùng lúc.

Đang có:

- Nhiều row giao dịch trong một form.
- Keyboard navigation giữa các ô, bao gồm text input và dropdown.
- Date cần thanh toán tự có ngày hôm nay và không cho chọn ngày sớm hơn hôm nay.
- Nếu dòng là mua thiết bị, hiển thị ô vòng đời thiết bị.
- Nếu không phải mua thiết bị, chỉ hiển thị ghi chú.

### 6. Lịch sử giao dịch

Route: `/transactions/history/`

Mục tiêu: xem, tìm kiếm, lọc, sửa, xóa và xác nhận thanh toán cho tất cả giao dịch.

Đang có:

- Header giống bảng theo dõi.
- Nút `Thêm giao dịch lẻ` và `Thêm nhiều giao dịch`.
- Bộ lọc thời gian: `Tất cả`, `Hôm nay`, `7 ngày`, `Tháng này`, date range.
- Tìm kiếm chi tiết theo sản phẩm, mã SP, đối tác, khách hàng, giá trị, mã lô, trạng thái thanh toán.
- KPI 6 card:
  - Doanh thu ghi nhận
  - Chi phí ghi nhận
  - Lợi nhuận ghi nhận
  - Tiền đã thu
  - Tiền đã chi
  - Dòng tiền thuần
- Tooltip giải thích các KPI.
- Tab loại giao dịch:
  - Tất cả
  - Doanh thu
  - Nhập hàng
  - Chi phí khác
  - Có hỗ trợ Shift + click để chọn nhiều loại.
- Bảng giao dịch:
  - Loại, ngày, nội dung, đối tác, số lượng, giá trị, thanh toán, hành động.
  - Sort/filter theo các cột.
  - Giao dịch mới lưu gần nhất được xếp lên trên nếu không chọn sort thủ công.
  - Nút sửa/xóa.
  - Nút nhanh `Đã thanh toán hôm nay` cho khoản chưa thanh toán.

### 7. Phân tích thêm

Route: `/report/`

Mục tiêu: phân tích sâu hơn về doanh thu, chi phí, lợi nhuận, dòng tiền và tồn kho.

Đang có:

- Bộ lọc thời gian dùng chung: hôm nay, 7 ngày, tháng này, date range, tất cả.
- KPI 6 card giống dashboard:
  - Doanh thu ghi nhận
  - Chi phí ghi nhận
  - Lợi nhuận ghi nhận
  - Tiền vào
  - Tiền ra
  - Dòng tiền thuần
- Biểu đồ phân tích doanh thu:
  - Doanh thu và lợi nhuận theo kỳ.
  - Trục Y co giãn theo dữ liệu, có hỗ trợ lợi nhuận âm.
  - Hover hiển thị kỳ, chỉ số, giá trị.
  - Bảng bên phải có phân cấp danh mục và nút +/-.
- Phân tích dòng tiền:
  - Tiền vào, tiền ra, dòng tiền thuần.
  - Tách rõ khỏi phân tích lãi/lỗ ghi nhận.
- Phân tích chi phí:
  - Donut chart.
  - Tooltip trắng theo từng lát: tên nhóm chi phí và tiền.
  - Bảng chi phí theo nhóm.
- Phân tích lợi nhuận:
  - Chọn theo danh mục hoặc theo sản phẩm.
  - Chọn tất cả danh mục hoặc một danh mục cụ thể.
  - Chọn Top 10, Bottom 10 hoặc Tất cả.
  - Bảng bên trái có doanh thu, lợi nhuận, biên lợi nhuận.
  - Biểu đồ ngang bên phải:
    - Bar = lợi nhuận.
    - Dot = biên lợi nhuận.
    - Legend cho lợi nhuận dương, lợi nhuận âm, biên lợi nhuận.
    - Tooltip trắng có format nhiều dòng: doanh thu, lợi nhuận, biên lợi nhuận.
- Tổng quan hàng tồn kho.
- Ranking panel:
  - Sản phẩm bán chạy nhất.
  - Danh mục biên lợi nhuận cao.
  - Sản phẩm tồn kho nhiều nhất.
  - Dòng tiền thuần.
  - Lãi/lỗ theo khấu hao.
  - Nhà cung cấp lớn nhất.

## Model dữ liệu chính

### Product

Lưu sản phẩm và trạng thái tồn kho.

Field quan trọng:

- `name`
- `category`
- `unit`
- `alert_threshold`
- `price_sell`
- `price_buy_latest`
- `supplier_name`
- `stock_quantity`
- `is_active`

Logic:

- `stock_status` trả về:
  - `het_hang` nếu tồn kho <= 0
  - `sap_het` nếu tồn kho <= ngưỡng cảnh báo
  - `day_du` nếu còn đủ

### Category

Lưu danh mục dạng path, ví dụ:

```text
Đồ ăn
Đồ ăn / Mì
Đồ ăn / Mì / Mì tôm
```

Field:

- `path`
- `name`
- `note`

### OpeningStock

Lưu tồn kho khởi điểm khi bắt đầu dùng app.

Logic:

- Khi tạo/sửa, tự cộng/chỉnh `Product.stock_quantity`.
- Khi xóa, tự trừ lại tồn kho.
- Nếu có `estimated_unit_cost`, cập nhật `Product.price_buy_latest`.

### Purchase

Lưu giao dịch nhập hàng.

Field quan trọng:

- `product`
- `date`
- `supplier_name`
- `quantity`
- `unit_price`
- `total_amount`
- `payment_method`
- `payment_due_date`
- `payment_date`
- `note`

Logic:

- `total_amount = quantity * unit_price`.
- Khi tạo/sửa, tự cộng tồn kho.
- Khi đổi sản phẩm trong giao dịch nhập, hoàn lại tồn kho sản phẩm cũ và cộng sang sản phẩm mới.
- Khi xóa, tự trừ tồn kho.
- Cập nhật `price_buy_latest` và `supplier_name` cho sản phẩm.
- Nếu thanh toán ngay, set `payment_date = date`.
- Nếu nợ/chưa thanh toán, giữ `payment_due_date`, `payment_date = None`.
- Không cho ngày cần thanh toán sớm hơn hôm nay.

### Sale

Lưu giao dịch bán hàng/doanh thu.

Field quan trọng:

- `product`
- `date`
- `customer_name`
- `quantity`
- `unit_price`
- `total_amount`
- `payment_method`
- `payment_due_date`
- `payment_date`
- `note`

Logic:

- `total_amount = quantity * unit_price`.
- Khi tạo/sửa, tự trừ tồn kho.
- Khi đổi sản phẩm trong giao dịch bán, hoàn lại tồn kho sản phẩm cũ và trừ sang sản phẩm mới.
- Khi xóa, tự cộng lại tồn kho.
- Form kiểm tra không cho bán quá tồn kho hiện có.
- Nếu thanh toán ngay, set `payment_date = date`.
- Nếu khách nợ, giữ `payment_due_date`, `payment_date = None`.

### Expense

Lưu chi phí khác.

Field quan trọng:

- `date`
- `expense_type`
- `amount`
- `estimated_lifetime_months`
- `payment_method`
- `payment_due_date`
- `payment_date`
- `note`

Nhóm chi phí hiện có:

- Tiền điện
- Tiền nước
- Tiền mặt bằng
- Lương
- Vận chuyển
- Mua thiết bị
- Khác

Logic:

- `amount` phải > 0.
- Nếu `expense_type = equipment`, bắt buộc có `estimated_lifetime_months`.
- Nếu không phải mua thiết bị, xóa `estimated_lifetime_months`.
- Nếu thanh toán ngay, set `payment_date = date`.
- Nếu nợ/chưa thanh toán, giữ `payment_due_date`, `payment_date = None`.

## Logic backend quan trọng

### 1. Ghi nhận lãi/lỗ và dòng tiền là hai khái niệm khác nhau

App cố ý tách hai cách nhìn:

#### Ghi nhận

Dùng để xem kỳ này hoạt động kinh doanh lời/lỗ ra sao.

- Doanh thu ghi nhận: tính khi ghi nhận giao dịch bán hàng, kể cả khách chưa trả tiền.
- Chi phí ghi nhận: tính khi chi phí phát sinh, kể cả chưa thanh toán.
- Lợi nhuận ghi nhận: doanh thu ghi nhận - chi phí ghi nhận.

#### Dòng tiền

Dùng để xem tiền thật vào/ra.

- Tiền vào: chỉ tính giao dịch đã thu tiền.
- Tiền ra: chỉ tính giao dịch đã chi tiền.
- Dòng tiền thuần: tiền vào - tiền ra.

Ví dụ:

- Bán hàng 1.000.000đ nhưng khách chưa trả:
  - Doanh thu ghi nhận tăng 1.000.000đ.
  - Tiền vào chưa tăng.
- Nhập hàng 500.000đ nhưng chưa trả NCC:
  - Chi phí/giá vốn ghi nhận có thể tăng.
  - Tiền ra chưa tăng.

### 2. Khấu hao/phân bổ chi phí thiết bị

Nhóm chi phí `Mua thiết bị` không bị trừ hết một lần vào chi phí ghi nhận.

Backend dùng `recognized_expense_summary(start_date, end_date)` để tính chi phí ghi nhận:

- Chi phí thường: tính toàn bộ vào ngày phát sinh.
- Mua thiết bị:
  - Nếu có vòng đời ước tính, chia đều theo số tháng.
  - Chỉ tính phần khấu hao/phân bổ rơi vào kỳ đang xem.
  - Giúp lợi nhuận không bị méo chỉ vì mua một thiết bị lớn trong một tháng.

Ví dụ:

- Mua máy 12.000.000đ, vòng đời 12 tháng.
- Mỗi tháng chi phí ghi nhận khoảng 1.000.000đ.
- Dòng tiền vẫn ghi nhận tiền ra thật theo thời điểm đã thanh toán.

### 3. Cash flow

Backend dùng `cash_flow_summary(start_date, end_date)`.

Logic:

- Với Sale:
  - Chỉ tính vào tiền vào nếu đã thanh toán.
  - Ngày dòng tiền là `payment_date` nếu có, nếu không thì `date`.
- Với Purchase:
  - Chỉ tính vào tiền ra nếu đã thanh toán.
  - Ngày dòng tiền là `payment_date` nếu có, nếu không thì `date`.
- Với Expense:
  - Chỉ tính vào tiền ra nếu đã thanh toán.
  - Ngày dòng tiền là `payment_date` nếu có, nếu không thì `date`.

### 4. Công nợ và cảnh báo thanh toán

Các giao dịch có `payment_method = debt` được coi là chưa thanh toán.

Backend có các helper tạo alert:

- Khách chưa thanh toán: từ Sale nợ.
- Cần thanh toán cho NCC: từ Purchase nợ.
- Cần thanh toán chi phí: từ Expense nợ.

Logic cảnh báo:

- Mặc định cảnh báo trước hạn 7 ngày.
- Có thể chỉnh ngưỡng bằng form trong dashboard, lưu vào session.
- Khoản quá hạn hoặc sắp đến hạn sẽ hiện ở dashboard/inventory.
- Mỗi alert có nút nhanh `Đã thanh toán hôm nay`.

Khi user bấm `Đã thanh toán hôm nay`:

- Route: `/transactions/<kind>/<pk>/mark-paid/`
- Backend đổi `payment_method` thành thanh toán ngay/chuyển khoản tùy logic hiện tại.
- Set `payment_date = today`.
- Xóa `payment_due_date`.
- Redirect về trang trước.

### 5. Tồn kho

Tồn kho được cập nhật tự động qua model `save()`/`delete()`:

- OpeningStock tạo: cộng tồn kho.
- OpeningStock xóa: trừ tồn kho.
- Purchase tạo: cộng tồn kho.
- Purchase xóa: trừ tồn kho.
- Sale tạo: trừ tồn kho.
- Sale xóa: cộng tồn kho.
- Sửa giao dịch sẽ tính chênh lệch so với số lượng cũ.

Điều này giúp bảng tồn kho luôn phản ánh dữ liệu giao dịch.

## Frontend và giao diện

### CSS

File CSS chính được import qua `core/static/core/css/styles.css`:

```css
@import url('./base.css');
@import url('./sidebar.css');
@import url('./dashboard.css');
@import url('./transactions.css');
@import url('./history.css');
@import url('./products.css');
@import url('./analytics.css');
@import url('./responsive.css');
@import url('./onboarding.css');
```

Ý nghĩa:

- `base.css`: biến màu, reset, layout nền.
- `sidebar.css`: sidebar, navigation.
- `dashboard.css`: bảng theo dõi.
- `transactions.css`: form giao dịch lẻ/bulk.
- `history.css`: lịch sử giao dịch.
- `inventory.css`: sản phẩm và tồn kho.
- `analytics.css`: phân tích thêm/report.
- `responsive.css`: responsive chung.

### JavaScript

- `core/static/core/js/inventory.js`
  - Filter/sort bảng sản phẩm.
  - Search topbar.
  - Popover filter cột.
  - Inline update tồn kho/ngưỡng.
  - Quản lý tab sản phẩm/danh mục/NCC.
- `core/static/core/js/chart.js`
  - Chart.js cho doanh thu, chi phí, dòng tiền.
  - Tooltip chart.
  - Render một số chart canvas.

### UI pattern đang dùng

- Card KPI có tooltip dấu `?`.
- Các bảng có filter/sort theo cột.
- Các cảnh báo có CTA rõ: xem giao dịch, nhập thêm hàng, đã thanh toán.
- Chart có legend, tooltip, data label khi cần.
- Cố gắng tách rõ:
  - Ghi nhận/lãi lỗ
  - Dòng tiền thật
  - Công nợ chưa thanh toán
  - Khấu hao/phân bổ thiết bị

## Các route chính

```text
/                                      Landing
/login/                                Đăng nhập
/signup/                               Đăng ký
/setup/products/                       Thiết lập sản phẩm và hàng ban đầu

/dashboard/                            Bảng theo dõi
/inventory/                            Sản phẩm và tồn kho
/report/                               Phân tích thêm

/transactions/create/                  Ghi nhận giao dịch lẻ
/transactions/bulk-create/             Ghi nhận nhiều giao dịch
/transactions/history/                 Lịch sử giao dịch
/transactions/<kind>/<pk>/mark-paid/   Xác nhận đã thanh toán

/sales/create/                         Tạo giao dịch bán hàng
/expenses/create/?mode=purchase        Tạo giao dịch nhập hàng
/expenses/create/                      Tạo chi phí khác

/products/create/                      Tạo sản phẩm
/products/delete/<pk>/                 Xóa sản phẩm

/inventory/products/<pk>/inline-update/
/inventory/categories/create/
/inventory/categories/rename/
/inventory/categories/delete/
/inventory/categories/bulk-move/
```

## Cách chạy local

Yêu cầu:

- Python 3.10+
- Django 5.2.x

Cài đặt tối thiểu:

```bash
python -m venv venv
venv\Scripts\activate
pip install django
```

Chạy migration:

```bash
python manage.py migrate
```

Chạy server:

```bash
python manage.py runserver
```

Mở:

```text
http://127.0.0.1:8000/
```

Kiểm tra cấu hình Django:

```bash
python manage.py check
```

## Ghi chú dữ liệu và hạn chế hiện tại

- Database local đang dùng SQLite.
- Chưa có hệ thống phân quyền người dùng thực sự theo doanh nghiệp/cửa hàng; nhiều text user hiện đang hard-code trong giao diện.
- Một số text trong model/form cũ từng bị mojibake; UI chính đã được sửa nhiều phần, nhưng nên tiếp tục chuẩn hóa toàn bộ source về UTF-8.
- Chưa có trang riêng cho `Cần thu / cần trả`; hiện công nợ nằm trong dashboard, inventory và lịch sử giao dịch.
- Chưa có trang riêng cho `Thiết bị & khấu hao`; hiện logic khấu hao đã có trong backend và report, nhưng nên bổ sung màn hình theo dõi thiết bị sau.

## Gợi ý phát triển tiếp

1. Tạo trang riêng `Thanh toán & công nợ`
   - Danh sách khách cần thu.
   - Danh sách NCC/chi phí cần trả.
   - Quá hạn/sắp đến hạn/chưa có hạn.
   - Nút xác nhận thanh toán, sửa hạn, xem giao dịch.

2. Tạo tab hoặc trang `Thiết bị & khấu hao`
   - Tên thiết bị/nhóm chi phí.
   - Ngày mua.
   - Giá trị mua.
   - Vòng đời ước tính.
   - Đã phân bổ bao nhiêu.
   - Còn lại bao nhiêu.
   - Chi phí phân bổ mỗi kỳ.

3. Chuẩn hóa encoding
   - Sửa toàn bộ mojibake còn lại trong model/form/sidebar.
   - Đảm bảo file lưu UTF-8.

4. Tách service layer
   - Hiện nhiều logic nghiệp vụ nằm trong `views.py`.
   - Nên tách các phần như cash flow, recognized expense, payment alerts, profit analytics sang module riêng để dễ test.

5. Thêm test tự động
   - Test cập nhật tồn kho khi tạo/sửa/xóa Sale/Purchase/OpeningStock.
   - Test cash flow chỉ tính giao dịch đã thanh toán.
   - Test chi phí mua thiết bị được phân bổ theo vòng đời.
   - Test alert thanh toán theo ngưỡng ngày.
