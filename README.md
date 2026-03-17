# ISD - Automated Global Tech Intelligence & Security Watchdog

ISD (Intelligent Software Developer) là một hệ sinh thái tự động hóa toàn diện quy trình thu thập và xử lý thông tin từ mọi nguồn trên thế giới.

## 🌟 Tính năng cốt lõi

- **Auto-Crawl:** Tự động theo dõi và cào dữ liệu từ các nguồn RSS/Web bất kỳ trên toàn cầu.
- **AI-Processing:** Tự động dịch và tóm tắt nội dung sang tiếng Việt bằng LLM (Ollama/vLLM).
- **Security Watchdog:** Phân tích và phát hiện sớm các cảnh báo bảo mật, lỗ hổng (CVE) và sự cố hạ tầng.
- **Interview Prep Track:** Chuyển đổi tin tức khô khan thành bộ câu hỏi phỏng vấn thực chiến (Case study, Troubleshooting, Interview tips).
- **Interactive Hub:** Giao diện Dashboard hiện đại và Chatbot AI hỗ trợ giải đáp kỹ thuật 24/7.

## 🚀 Cài đặt nhanh (Dành cho Linux)

1. **Tải mã nguồn:**
   ```bash
   git clone <URL_REPO_CUA_SEP>
   cd isd-distribution
   ```

2. **Cài đặt công cụ quản lý `isd`:**
   ```bash
   ./bootstrap.sh
   ```

3. **Cài đặt toàn bộ hệ thống:**
   ```bash
   isd install
   ```

## 🛠 Lệnh quản lý (ISD CLI)

- `isd start`: Khởi động toàn bộ pipeline và web dashboard.
- `isd stop`: Dừng các dịch vụ đang chạy ngầm.
- `isd restart`: Khởi động lại hệ thống.
- `isd status`: Kiểm tra tình trạng vận hành của các dịch vụ.
- `isd model <name>`: Thay đổi model AI xử lý (VD: `isd model qwen3:30b`).

---
"Biến tin tức thế giới thành kiến thức thực chiến của bạn."
