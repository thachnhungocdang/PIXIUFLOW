# 🌟 Pixiu Flow - Nền tảng Quản lý Tài chính Doanh nghiệp Thông minh

Chào mừng bạn đến với mã nguồn của **Pixiu Flow**! Tài liệu này được biên soạn nhằm giúp các lập trình viên, giảng viên hoặc bất kỳ ai tiếp quản dự án có thể nắm bắt toàn diện **luồng logic (Logic Flow)**, **cấu trúc thiết kế (Design)** và **các thành phần mã nguồn (Codebase)** của toàn bộ website.

---

## 1. Tổng quan Hệ thống (Overview)
**Pixiu Flow** là một ứng dụng Web Application được thiết kế dành riêng cho các chủ doanh nghiệp nhỏ/cửa hàng. Hệ thống giúp theo dõi dòng tiền (Cashflow), ghi nhận giao dịch (Doanh thu & Chi phí), quản lý hàng tồn kho (Inventory) và cung cấp các báo cáo phân tích chuyên sâu (Analytics).

**Công nghệ sử dụng (Tech Stack):**
- **Backend:** Python, Django Framework.
- **Frontend:** HTML5, CSS3 thuần (Vanilla CSS), JavaScript (Vanilla JS).
- **Cơ sở dữ liệu:** SQLite (hoặc PostgreSQL tùy môi trường triển khai).
- **Kiến trúc:** MVT (Model - View - Template) đặc trưng của Django.

---

## 2. Kiến trúc Luồng Code (Code Flow Architecture)
Hệ thống tuân thủ chặt chẽ kiến trúc MVT, luồng dữ liệu (Data Flow) di chuyển qua các tầng như sau:

1. **User Request (Trình duyệt):** Người dùng thao tác trên giao diện (click nút, điền form). JavaScript thuần ở phía Client sẽ bắt sự kiện, tính toán tạm thời (như tính tổng tiền, check validate cơ bản) và định dạng giao diện động.
2. **Routing (`core/urls.py`):** Khi form được Submit hoặc AJAX gọi lên, hệ thống URL của Django sẽ điều hướng Request đến đúng View xử lý.
3. **Controller/Logic (`core/views.py`):** Chứa toàn bộ logic nghiệp vụ (Business Logic). View sẽ kiểm tra quyền, xác thực form (`core/forms.py`), và gọi các hàm tính toán phức tạp.
4. **Database/Models (`core/models.py`):** View sẽ tương tác với Models để truy vấn (Query) hoặc thay đổi dữ liệu (Insert/Update) vào cơ sở dữ liệu.
5. **Render/Response (`core/templates/core/`):** Sau khi xử lý xong, View sẽ đóng gói dữ liệu truyền vào file HTML (Django Template) để kết xuất giao diện hoặc trả về cục bộ JSON (đối với AJAX) cho người dùng.

---

## 3. Luồng Nghiệp vụ Cụ thể (Business Logic Flow)
Dưới đây là các luồng vận hành chính của hệ thống Pixiu Flow:

### A. Luồng Đăng nhập & Thiết lập ban đầu (Onboarding)
- **Flow:** `Landing Page` ➔ `Đăng ký/Đăng nhập` ➔ `Thiết lập Cửa hàng` ➔ `Khai báo Tồn kho đầu kỳ`.
- **Logic:** Khi tài khoản mới được tạo, hệ thống yêu cầu thiết lập thông tin cơ bản. Dữ liệu "Tồn kho đầu kỳ" sẽ tạo ra các bản ghi Stock ban đầu trong Database làm cơ sở cho mọi tính toán xuất/nhập sau này.

### B. Luồng Ghi nhận Giao dịch (Doanh thu & Chi phí)
- **Flow:** `Chọn loại Giao dịch` ➔ `Điền Form (Sản phẩm, Số lượng, Đơn giá)` ➔ `Lưu Database` ➔ `Cập nhật Công nợ/Tồn kho` ➔ `Ghi nhận Lịch sử`.
- **Logic tinh gọn (Frontend):** Javascript xử lý tự động tính Thành tiền = Số lượng * Đơn giá. Nếu người dùng muốn tạo Sản phẩm mới trong lúc nhập giao dịch ➔ Bật Modal ➔ Dùng **AJAX (`fetch API`)** gửi ngầm lên Backend ➔ Backend tạo Product ➔ Trả về ID ➔ JS tự động nhét sản phẩm mới vào Dropdown mà không làm mất dữ liệu form đang nhập dở.
- **Logic Backend:** Khi lưu Chi phí Nhập hàng (Purchase), hệ thống đồng thời sinh ra 1 phiếu Chi tiền và tự động cộng (+) số lượng vào Tồn kho của sản phẩm tương ứng. Tương tự, Doanh thu (Sale) sẽ trừ (-) Tồn kho. Phương thức thanh toán (Tiền mặt / Công nợ) sẽ quyết định ngày đáo hạn.

### C. Luồng Quản lý Tồn kho & Cảnh báo (Inventory)
- **Logic:** Tồn kho không phải là một con số tĩnh bị gán tay, mà được tính toán động hoặc cập nhật tự động (Trigger) mỗi khi có Giao dịch Mua/Bán xảy ra.
- Giao diện Inventory sẽ đối chiếu số tồn hiện tại với `alert_threshold` (ngưỡng cảnh báo). Nếu thấp hơn, hệ thống tự đẩy sản phẩm đó lên danh sách "Cần nhập gấp".

### D. Luồng Phân tích & Báo cáo (Analytics)
- **Logic:** `views.py` tổng hợp dữ liệu từ các giao dịch trong tháng/năm, gom nhóm (group by) theo từng mảng (Doanh thu, Lợi nhuận, Chi phí theo danh mục).
- Dữ liệu được đưa về dạng chuỗi JSON `chart_points_json` truyền thẳng vào HTML. JavaScript phía Frontend sẽ đọc chuỗi JSON này và vẽ lên các biểu đồ (Bar, Line, Combo chart) tương ứng.

---

## 4. Thiết kế Giao diện (Design & UI/UX)
Giao diện của Pixiu Flow được xây dựng dựa trên bản thiết kế Figma với các nguyên tắc nghiêm ngặt:
- **Không sử dụng Framework CSS (No Bootstrap/Tailwind):** Toàn bộ giao diện được tôi "cắt" từ Figma bằng CSS thuần (Vanilla CSS) để kiểm soát tuyệt đối từng pixel, margin, padding, đảm bảo đúng 100% thiết kế gốc.
- **Cấu trúc File CSS:** Được chia nhỏ theo tính năng (ví dụ: `dashboard.css`, `transactions.css`, `analytics.css`) và quy về một mối quản lý Responsive qua `responsive.css`.
- **Grid/Flexbox Layout:** Hệ thống sử dụng CSS Grid đa chiều làm xương sống. Giao diện có khả năng tự động "chảy" (reflow) mượt mà từ màn hình máy tính lớn (1920px), Tablet (1024px) xuống đến giao diện Mobile (760px) mà không bị vỡ layout.

---

## 5. Vai trò và Những phần tôi đã Code (Developer's Contributions)
Trong dự án này, với vai trò **Fullstack Developer**, đầu vào của tôi là bộ Figma (Giao diện) và luồng mô tả tính năng từ các thành viên. Từ đó, **tôi đã tự tay lập trình toàn bộ hệ thống từ Frontend tới Backend**:

### Phần Frontend (Giao diện & Tương tác)
1. **Xây dựng toàn bộ HTML/CSS:** Viết code HTML chuẩn Semantic và toàn bộ các file CSS (`base.css`, `transactions.css`, `history.css`, `responsive.css`...) cấu thành nên giao diện hiện đại của hệ thống.
2. **Lập trình JavaScript (Client-side):** 
   - Viết các logic ẩn/hiện động các trường thông tin (VD: Chọn "Thiết bị" sẽ hiện ô nhập "Khấu hao tháng").
   - Viết logic gộp/chèn hàng loạt (Bulk Create) bằng JS để người dùng nhập nhiều giao dịch như đang xài Excel.
   - Quản lý logic điều hướng tab (`data-main-tab`, `data-profit-tabs`) trong màn hình Report mà không cần load lại trang.

### Phần Backend (Logic Server)
1. **Thiết kế Database Models (`core/models.py`):** Lập trình các Model như `Transaction`, `Expense`, `Product`, `Category`, định nghĩa các mối quan hệ (Foreign Key) và quy tắc cơ sở dữ liệu.
2. **Xây dựng Business Logic (`core/views.py`):** 
   - Viết các View xử lý lưu dữ liệu, bắt lỗi Form (`core/forms.py`).
   - Xây dựng luồng logic tính toán lợi nhuận, doanh thu, dòng tiền theo các bộ lọc thời gian (Start Date / End Date).
3. **Phát triển API tĩnh:** Cung cấp các AJAX endpoint (như luồng tạo nhanh Product khi đang nhập Expense) để kết nối đồng bộ giữa Backend và JS phía Frontend.

---

## 6. Hướng dẫn Cài đặt & Khởi chạy (Local Setup)
Dành cho người mới muốn chạy source code này trên máy cá nhân:

**Bước 1: Cài đặt môi trường ảo và thư viện**
```bash
python -m venv venv
venv\Scripts\activate   # Trên Windows
# source venv/bin/activate # Trên Mac/Linux
pip install -r requirements.txt
```

**Bước 2: Migrate Cơ sở dữ liệu**
```bash
python manage.py makemigrations core
python manage.py migrate
```

**Bước 3: Khởi chạy Server**
```bash
python manage.py runserver
```
Sau đó mở trình duyệt và truy cập: `http://127.0.0.1:8000/`

---
*Pixiu Flow - Tối ưu hóa dòng tiền, Đơn giản hóa quản trị.*
