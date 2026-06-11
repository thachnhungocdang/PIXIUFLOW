# Báo cáo cá nhân — Đặng Như Ngọc Thạch (2312380032)

## Vai trò trong dự án

Trong dự án Pixiu Flow, tôi đảm nhận vai trò Fullstack Developer: tiếp nhận logic nghiệp vụ, sitemap và thiết kế Figma từ các thành viên phụ trách nghiên cứu/UI/UX, sau đó hiện thực thành ứng dụng Django hoàn chỉnh. Tôi xây dựng cả backend Python/Django, Django Templates, CSS và JavaScript thuần; đồng thời cấu hình triển khai Railway và sửa lỗi phát hiện trong các buổi kiểm thử chung của nhóm.

## Dấu ấn cá nhân trong sản phẩm

Dấu ấn rõ nhất của tôi là luồng dữ liệu xuyên suốt từ ghi nhận giao dịch đến dashboard và trang phân tích. Cụ thể, dữ liệu từ `sale_form.html`, `expense_form.html` và `bulk_transaction_form.html` được kiểm tra, lưu qua các model `Sale`, `Purchase`, `Expense`, rồi đi vào các hàm `cogs_summary`, `recognized_expense_summary`, `cash_flow_summary` để tạo báo cáo doanh thu, lợi nhuận, chi phí và dòng tiền trong `report.html`.

Một phần tôi đầu tư nhiều là tab **Chi phí**: tính tổng chi phí theo kỳ, chi phí/ngày, tỷ lệ chi phí/doanh thu, khấu hao theo vòng đời, cảnh báo chi vượt doanh thu, so sánh kỳ trước và insight về nhóm chi phí mới phát sinh. Tôi cũng trực tiếp dựng các biểu đồ tương tác bằng SVG/JavaScript trong `core/templates/core/report.html`, thay vì phụ thuộc vào thư viện biểu đồ bên ngoài.

## Những việc đã thực sự làm

- Chuyển các thiết kế Figma thành các màn hình landing, đăng ký/đăng nhập, onboarding, dashboard, sản phẩm và tồn kho, form giao dịch, lịch sử giao dịch và trang phân tích bằng Django Templates, CSS và responsive layout.
- Xây dựng các model `Product`, `Category`, `OpeningStock`, `Purchase`, `Sale`, `Expense` trong `core/models.py`; xử lý cập nhật tồn kho khi nhập, bán, sửa hoặc xóa giao dịch.
- Implement các luồng ghi nhận doanh thu, nhập hàng, chi phí lẻ và nhập nhiều giao dịch; hỗ trợ tạo sản phẩm ngay trong form bằng `fetch()` qua hai endpoint `sale_new_product_ajax_view` và `expense_new_product_ajax_view`.
- Viết logic tài chính gồm doanh thu ghi nhận, giá vốn tại thời điểm bán, lợi nhuận gộp/thuần, tiền thực thu/thực chi, dòng tiền thuần, công nợ và phân bổ chi phí theo thời gian sử dụng.
- Xây dựng trang `/report/` với các tab Doanh thu, Lợi nhuận, Chi phí và Dòng tiền; hỗ trợ lọc kỳ, phân tích theo sản phẩm/danh mục và biểu đồ tương tác.
- Xây dựng trang `/inventory/` với KPI tồn kho, giá trị tồn kho, cảnh báo chưa có tồn kho/hết hàng/sắp hết, sửa sản phẩm trực tiếp và quản lý cây danh mục nhiều cấp.
- Thêm hệ thống mã sản phẩm tự động theo danh mục trong `core/utils.py`, endpoint xem trước mã và các migration `0013`–`0015` để thêm, backfill và ràng buộc SKU.
- Cấu hình deploy bằng `Procfile`, Gunicorn, WhiteNoise, PostgreSQL qua `dj-database-url`, biến môi trường cho host/CSRF và chạy migration/collectstatic khi khởi động.
- Sửa các lỗi từ quá trình team testing: tổng tồn kho không cộng đúng hàng ban đầu và hàng nhập; card “Chưa có tồn kho” hiển thị sai điều kiện; dữ liệu kỳ trước của chi phí legacy bị tính thành 0; insight chỉ liệt kê một nhóm chi phí mới; thứ tự/cột trên form khai báo hàng ban đầu và cách hiển thị mã sản phẩm.
- Viết test hồi quy trong `core/tests.py` cho SKU, tổng tồn kho, card sản phẩm chưa có tồn kho, dữ liệu chi phí kỳ trước và insight nhiều nhóm chi phí mới.

## File, tính năng, logic đã đóng góp

| Phần | File / Path | Mô tả |
|------|-------------|-------|
| Database | `core/models.py` | Model sản phẩm, danh mục, tồn kho ban đầu, nhập hàng, bán hàng và chi phí; validation thanh toán và cập nhật tồn kho. |
| Migration | `core/migrations/0001_initial.py` – `0015_add_sku_unique.py` | Phát triển schema, thêm theo dõi thanh toán, `cogs_amount`, user scope, thời gian sử dụng chi phí và SKU. |
| Logic tài chính | `core/views.py` | Các hàm `recognized_expense_summary`, `cogs_summary`, `cash_flow_summary`, `build_payment_alerts` và logic tổng hợp KPI/báo cáo. |
| Dashboard | `core/templates/core/dashboard.html`, `core/static/core/css/dashboard.css` | KPI doanh thu, lợi nhuận, dòng tiền, cảnh báo thanh toán và biểu đồ xu hướng. |
| Sản phẩm & tồn kho | `core/templates/core/inventory.html`, `core/static/core/css/inventory.css`, `core/static/core/js/inventory.js` | Quản lý kho, danh mục, nhà cung cấp, lọc/sắp xếp, inline edit và cảnh báo tồn kho. |
| Giao dịch | `sale_form.html`, `expense_form.html`, `bulk_transaction_form.html`, `transactions.css` | Form doanh thu, nhập hàng, chi phí và nhập nhiều giao dịch; modal tạo sản phẩm và tính thành tiền phía client. |
| Lịch sử | `transaction_history.html`, `history.css` | Tìm kiếm, bộ lọc, sắp xếp, sửa/xóa, đánh dấu đã thanh toán và gia hạn công nợ. |
| Phân tích | `core/templates/core/report.html`, `core/static/core/css/analytics.css` | Bốn tab phân tích, KPI, bảng cây danh mục, biểu đồ SVG, tooltip, cảnh báo và insight. |
| Onboarding | `setup_products.html`, `onboarding.css` | Khai báo sản phẩm và tồn kho ban đầu theo nhiều dòng, kèm hướng dẫn và validation. |
| Authentication/UI chung | `landing.html`, `login.html`, `signup.html`, `base.html`, `sidebar.css`, `responsive.css` | Luồng vào hệ thống, layout chung, sidebar và responsive. |
| SKU | `core/utils.py`, `preview_product_sku` | Chuẩn hóa tiếng Việt, sinh prefix từ danh mục và mã sản phẩm tuần tự theo từng user. |
| Test | `core/tests.py` | Test SKU, inventory summary và các lỗi hồi quy của báo cáo chi phí. |
| Deploy | `Procfile`, `config/settings.py`, `requirements.txt` | Chạy migration, collectstatic, Gunicorn; cấu hình database, static files, host và CSRF cho production. |

## Bằng chứng đóng góp

- Repository: <https://github.com/thachnhungocdang/PIXIUFLOW>
- Commit history: toàn bộ 15 commit hiện có được ghi nhận dưới tác giả `Ngọc Thạch <thach.ngocdang25@gmail.com>`; có thể kiểm tra bằng `git log --author="Ngọc Thạch" --oneline`.
- Commit deploy tiêu biểu: `f13755e add Procfile for Railway deploy`, `ee4538f fix production settings`, `5f461aa fix csrf trusted origins`.
- Commit tính năng/sửa lỗi tiêu biểu: `b9ea9dd update charts, auth, onboarding flow`, `b220083 Fix analytics chart tooltip and profit colors`, `faf410a submit Pixiu Flow project`.
- Pull requests: [CẦN BỔ SUNG: link Pull Request nếu nhóm có sử dụng quy trình PR].
- Demo Railway: [CẦN BỔ SUNG: URL website Railway đang hoạt động].
- Kiểm thử: `core/tests.py` hiện có test tự động cho SKU, tồn kho và báo cáo chi phí; lệnh chạy là `python manage.py test`.

## Phần đóng góp kết nối với sản phẩm cuối như thế nào

Phần frontend tôi triển khai giúp người dùng đi theo một hành trình liền mạch: đăng ký, khai báo hàng ban đầu, ghi nhận bán hàng/nhập hàng/chi phí, rồi kiểm tra kết quả trên dashboard và báo cáo. Phần backend bảo đảm mỗi thao tác đó cập nhật đúng tồn kho, giá vốn, trạng thái thanh toán và các chỉ số tài chính, nhờ vậy người dùng có thể ra quyết định dựa trên dữ liệu thay vì tự tổng hợp bằng bảng tính.

Việc triển khai lên Railway biến bản thiết kế và source code thành một sản phẩm có thể truy cập để giảng viên và người dùng thử trực tiếp. Các đợt sửa lỗi sau team testing giúp kết quả trên giao diện khớp hơn với dữ liệu thật, đặc biệt ở tồn kho, kỳ so sánh chi phí và cách diễn giải insight.

## Điều cá nhân học được

- Tôi hiểu rõ hơn sự khác nhau giữa lãi/lỗ ghi nhận và dòng tiền: `Purchase` làm tăng tồn kho nhưng chưa phải giá vốn; COGS chỉ được ghi nhận khi `Sale` phát sinh, còn cash flow phụ thuộc vào ngày thanh toán.
- Tôi học cách thiết kế một luồng dữ liệu fullstack trong Django: từ validation ở form/model, xử lý trong view, truy vấn theo user, truyền context sang template và cập nhật giao diện bằng JavaScript.
- Tôi cải thiện kỹ năng chuyển Figma thành giao diện có thể sử dụng thật, bao gồm responsive table, modal, tooltip, trạng thái rỗng, cảnh báo và các trường hợp dữ liệu dài.
- Tôi có thêm kinh nghiệm dựng biểu đồ SVG tương tác, xử lý scale, tooltip, legend, stacked columns và dữ liệu âm/dương mà không dùng thư viện chart.
- Tôi học được giá trị của test hồi quy: sau khi sửa lỗi tồn kho hoặc kỳ trước, test trong `core/tests.py` giúp tránh việc lỗi cũ quay lại khi thay đổi logic liên quan.

## Khó khăn đã gặp và cách xử lý

- **Tách lợi nhuận khỏi dòng tiền:** Ban đầu rất dễ cộng toàn bộ tiền nhập hàng vào chi phí. Tôi tách logic thành `cogs_summary()` và `cash_flow_summary()`: nhập hàng chỉ là cash out khi đã trả, còn giá vốn được lấy từ `Sale.cogs_amount`. Migration `0009_sale_cogs_amount.py` backfill giá vốn cho dữ liệu bán hàng cũ.
- **Phân bổ chi phí theo thời gian sử dụng:** Một khoản thiết bị hoặc chi phí hưởng lợi nhiều tháng không thể tính hết vào tháng mua. Tôi xây dựng `recognized_expense_summary()` với `month_start_date`, `add_months_date`, `month_count_between` để tính phần chi phí giao với từng kỳ báo cáo.
- **Dữ liệu cũ không có user:** Một số bản ghi legacy có `user_id=NULL`, khiến kỳ trước hiển thị 0 dù database có chi phí. Tôi thêm `expenses_for_user()` để nhận diện dữ liệu legacy trong trường hợp chỉ có một chủ dữ liệu, đồng thời viết test bảo đảm không chia sẻ dữ liệu đó khi tồn tại nhiều owner.
- **Biểu đồ và bảng lớn trên nhiều kích thước màn hình:** `report.html` và `inventory.html` chứa nhiều cột và tương tác. Tôi dùng CSS theo từng page, vùng scroll, grid responsive và JavaScript render lại SVG theo kích thước container.
- **Tạo sản phẩm ngay trong lúc nhập giao dịch:** Để không làm mất dữ liệu form đang nhập, tôi dùng `fetch()` gọi endpoint AJAX, lưu sản phẩm ở backend rồi đưa sản phẩm mới trở lại dropdown mà không reload toàn trang.

## Lời nhắn cho sinh viên khóa sau

- Trước khi code báo cáo tài chính, hãy thống nhất rõ khái niệm doanh thu ghi nhận, tiền thực thu, giá vốn, chi phí và dòng tiền; sai định nghĩa sẽ làm toàn bộ KPI sai dù giao diện đẹp.
- Khi sửa `core/views.py`, nên tìm đúng helper bằng `rg` và kiểm tra các trang đang dùng helper đó, vì file hiện chứa nhiều logic dùng chung giữa dashboard, history và report.
- Hãy lưu giá vốn tại thời điểm bán như `Sale.cogs_amount`; không nên luôn lấy giá nhập mới nhất khi xem lại giao dịch cũ.
- Với form nhiều dòng hoặc modal AJAX, cần thử cả trường hợp validation lỗi, dữ liệu rỗng và người dùng đã nhập dở trước khi mở modal.
- Sau mỗi bug quan trọng, hãy thêm test hồi quy và chạy `python manage.py check` cùng `python manage.py test` trước khi deploy.
