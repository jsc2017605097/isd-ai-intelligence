# ISDNews Hub (tách service)

## Mục tiêu
- Service riêng cho web tin tức đẹp, không đụng logic core hiện tại.
- Chỉ đọc dữ liệu từ DB hiện tại (`/home/khiemtv/sources/isdnews/db.sqlite3`).

## Thành phần
- `isdnews-hub-api`: API đọc bài viết/filter/chi tiết/digest/TTS mode
- `isdnews-hub-web`: giao diện clean editorial
- `isdnews-hub-worker`: job nhóm bài liên quan
- `isdnews-hub-scheduler`: trigger worker mỗi 30 phút

## Chạy với PM2
```bash
cd /home/khiemtv/sources/isdnews-hub
pm2 start ecosystem.config.cjs
pm2 status
pm2 logs isdnews-hub-api
```

## Cổng mặc định
- API: `http://127.0.0.1:8787`
- Web: `http://127.0.0.1:4173`

## API nhanh
- `GET /api/articles?q=&team=&source=&page=&pageSize=`
- `GET /api/articles/:id`
- `GET /api/teams`
- `GET /api/sources`
- `GET /api/digest/today`
- `GET /api/tts/:articleId`

## Biến môi trường (`.env`)
- `SOURCE_DB_PATH`: DB nguồn isdnews (read-only)
- `HUB_DB_PATH`: DB phụ trợ của hub
- `LOCAL_TTS_ENDPOINT`: endpoint TTS local (nếu có)
