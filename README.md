# ISD Ecosystem (All-in-One)

Hệ sinh thái tóm tắt tin tức và ôn luyện phỏng vấn công nghệ thực chiến.

## 🚀 Cài đặt nhanh (Dành cho Linux)

1. **Tải mã nguồn:**
   ```bash
   git clone <URL_CUA_SEP>
   cd isd-distribution
   ```

2. **Cài đặt công cụ quản lý `isd`:**
   ```bash
   ./bootstrap.sh
   ```

3. **Cài đặt toàn bộ hệ thống (tự động):**
   ```bash
   isd install
   ```

## 🛠 Lệnh quản lý

- `isd start`: Chạy tất cả dịch vụ (Worker, Beat, Hub API).
- `isd stop`: Dừng hệ thống.
- `isd status`: Kiểm tra tình trạng các dịch vụ.
- `isd model <name>`: Đổi model AI đang sử dụng (VD: `isd model qwen3:30b`).

---
Dự án được quản lý bởi `isd-cli`.
