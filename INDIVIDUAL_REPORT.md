# Báo cáo Cá nhân - Dự án Pixiu Flow

**Họ và tên:** [Điền tên của bạn]
**Mã sinh viên:** [Điền MSSV của bạn]

## 1. Vai trò trong dự án
**Vai trò chính:** Lập trình viên Fullstack (Fullstack Developer)
Trong dự án này, tôi là người trực tiếp xây dựng toàn bộ mã nguồn của hệ thống từ đầu đến cuối (End-to-End). Đầu vào của tôi là các bản thiết kế giao diện (Figma), luồng người dùng (Userflow) và tài liệu phân tích logic do các thành viên trong nhóm cung cấp. Từ đó, tôi đảm nhận việc lập trình cả mảng Frontend (giao diện người dùng) và Backend (xử lý dữ liệu, logic hệ thống, cơ sở dữ liệu) để tạo ra sản phẩm hoàn chỉnh chạy được trên thực tế.

## 2. Dấu ấn cá nhân trong sản phẩm
Dấu ấn rõ nét nhất của tôi là **sự liền mạch và hoàn thiện của toàn bộ hệ thống**. Tôi đã tự tay kết nối bản thiết kế tĩnh thành một ứng dụng động, nơi dữ liệu từ lúc người dùng nhập vào trên giao diện (Frontend) được kiểm tra, tính toán, sau đó lưu trữ an toàn và xử lý chính xác ở phía máy chủ (Backend), cuối cùng phản hồi kết quả lại màn hình một cách mượt mà.

## 3. Những việc đã thực sự làm
1. **Phát triển Frontend (Giao diện & Tương tác):** 
   - Chuyển đổi toàn bộ thiết kế từ Figma thành mã HTML/CSS (Responsive Layout).
   - Viết các đoạn mã JavaScript (Vanilla JS) để xử lý logic phía client: tính toán tổng tiền tự động, thêm/xóa dòng dữ liệu động, ẩn/hiện form theo ngữ cảnh người dùng thao tác.
2. **Phát triển Backend (Logic & Dữ liệu):** 
   - Dựa trên logic nhóm cung cấp, thiết kế cấu trúc Cơ sở dữ liệu (Models) trong Django.
   - Xây dựng các Views và Forms để xử lý dữ liệu gửi lên (POST requests), kiểm tra tính hợp lệ (Validation) và lưu vào database.
   - Viết các API/AJAX endpoints (ví dụ: tạo sản phẩm mới ngay trên form nhập liệu mà không cần load lại trang).
3. **Tích hợp hệ thống:** Kết nối giao diện HTML/CSS với Django Templates, đảm bảo dữ liệu từ Backend được hiển thị chính xác ra Frontend và ngược lại.

## 4. File, tính năng, dữ liệu, logic, giao diện, tài liệu đã đóng góp
Vì tôi phụ trách code toàn bộ, phần đóng góp trải dài khắp hệ thống. Tiêu biểu có thể kể đến:
- **Tính năng:** Toàn bộ hệ thống quản lý giao dịch (Doanh thu & Chi phí), Quản lý Kho, Dashboard hiển thị thống kê.
- **Backend (Python/Django):**
  - Hệ thống Models (`core/models.py`) thiết kế cấu trúc dữ liệu cho giao dịch, sản phẩm, chi phí.
  - Hệ thống Views (`core/views.py`) xử lý logic nghiệp vụ, tính toán công nợ, quản lý luồng dữ liệu.
- **Frontend (HTML/CSS/JS):**
  - Cụm giao diện nhập liệu phức tạp: `expense_form.html`, `sale_form.html`, `bulk_transaction_form.html`.
  - Hệ thống style: `transactions.css`, `responsive.css`.

## 5. Bằng chứng đóng góp
*(Lưu ý: Hãy thay thế phần này bằng link thực tế của bạn)*
- **Link Commit:** [Chèn link các commit GitHub của bạn. Ví dụ: "Commit xây dựng luồng tạo chi phí", "Commit hoàn thiện cấu trúc Database"]
- **Link Pull Request:** [Chèn link PR nếu có]
- **Ảnh chụp màn hình:** [Chèn 1-2 ảnh chụp hệ thống hoạt động thực tế, ví dụ form giao dịch hoặc Dashboard]
- **Chi tiết:** Toàn bộ lịch sử commit trong repository của dự án đều do tài khoản GitHub của tôi thực hiện, bao quát từ file tĩnh (CSS/JS) đến logic server (Python).

## 6. Phần đóng góp đó kết nối thế nào với sản phẩm cuối cùng
Phần công việc của tôi chính là cốt lõi kỹ thuật của sản phẩm. Nếu nhóm phân tích và thiết kế tạo ra "bản vẽ và vật liệu", thì tôi là người "thi công" để xây dựng nên "ngôi nhà" hoàn chỉnh. Không có phần code của tôi, thiết kế trên Figma và logic trên giấy sẽ không thể trở thành một phần mềm thực tế để người dùng có thể thao tác, tính toán và lưu trữ dữ liệu tài chính.

## 7. Điều cá nhân học được
- **Khả năng bao quát hệ thống (System Thinking):** Học được cách tư duy kết nối từ giao diện người dùng (UI) xuống tới các bảng trong cơ sở dữ liệu (Database). Hiểu rõ vòng đời của một luồng dữ liệu đi qua toàn bộ ứng dụng.
- **Quản lý thời gian & Cấu trúc Code:** Nhận ra tầm quan trọng của việc viết code sạch, tổ chức thư mục rõ ràng (chia file CSS, tách hàm logic) khi phải tự tay quản lý một khối lượng mã nguồn lớn (cả Frontend lẫn Backend).
- Kỹ năng xử lý các bài toán bất đồng bộ (AJAX/Fetch API) giữa Client và Server để tăng trải nghiệm người dùng.

## 8. Khó khăn đã gặp và cách xử lý
- **Khó khăn:** Một trong những thách thức lớn nhất là xử lý các luồng giao diện phức tạp có sự phụ thuộc logic chặt chẽ vào backend. Ví dụ: Trên form nhập chi phí, người dùng muốn "Thêm sản phẩm mới" ngay lập tức (hiện Modal) mà không muốn mất dữ liệu đang nhập dở trên form chính, sau đó sản phẩm vừa tạo phải xuất hiện ngay trong dropdown chọn sản phẩm.
- **Cách xử lý:** Thay vì submit lại toàn bộ trang (sẽ làm mất dữ liệu), tôi đã tìm hiểu và ứng dụng AJAX (dùng hàm `fetch()` trong JavaScript). Tôi viết một API nhỏ ở Backend (`/ajax-new-product/`) để nhận thông tin sản phẩm mới, lưu vào Database và trả về ID. Ở Frontend, JS sẽ bắt kết quả này và tự động chèn thêm một thẻ `<option>` mới vào dropdown, giúp trải nghiệm người dùng hoàn toàn liền mạch.

## 9. Lời nhắn cho sinh viên khóa sau
Khi đảm nhận việc code toàn bộ ứng dụng (Fullstack) dựa trên thiết kế và logic của người khác: **Hãy giao tiếp thật kỹ với team thiết kế và phân tích trước khi gõ dòng code đầu tiên.**
Đừng vội vàng code ngay. Hãy dành thời gian đọc kỹ Userflow, hiểu rõ đầu vào/đầu ra của từng màn hình. Nếu thấy thiết kế Figma phi thực tế hoặc logic bị thiếu (ví dụ: thiếu trường hợp báo lỗi, thiếu màn hình loading), hãy phản hồi lại cho team ngay lập tức. Sự phối hợp chặt chẽ giữa người code và người phân tích sẽ giúp bạn tránh phải đập đi xây lại hệ thống nhiều lần.
