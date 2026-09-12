# AbhiHub Technology Stack

## Backend
- **Language**: Python 3.13
- **Framework**: Flask 2.0+
- **WSGI / Worker**: Gunicorn with GeventWebSocketWorker
- **Realtime**: Flask-SocketIO / Gevent-WebSocket
- **Task Scheduling**: APScheduler

## Frontend
- **Rendering**: Jinja2 Server-Side Templates
- **Styling**: Tailwind CSS 3.4+ (PostCSS/Tailwind CLI)
- **Scripting**: Vanilla JavaScript (ES6+), Socket.IO client
- **Icons**: Lucide Icons, FontAwesome

## Data & Storage
- **Database**: Supabase PostgreSQL (Schema: `abhihub`)
- **Object Storage**: Cloudinary (primary for docs/images) + Supabase Storage / Firebase Storage (legacy fallback)
- **Push Service**: PyWebPush (VAPID)

## Analytics & Monitoring
- **Client Analytics**: Google Tag Manager / GA4 (`G-D5C3MDTQ3V`)
- **Server Analytics**: Custom Supabase telemetry (`page_views`, `file_access_history`, `error_logs`)
