# PDP One

نسخه پایه سامانه یکپارچه مدیریت پروژه، قرارداد، مناقصات و تحلیل‌های مدیریتی.

## Current milestone

- Persian RTL responsive dashboard and PWA manifest
- Contract, finance and receivables, project, tender, and analysis demonstration flows
- PostgreSQL-backed contract, receivable, payment-receipt and analysis drafts with audit events
- Authenticated finance API and browser session login
- Django REST API foundation with PostgreSQL models
- Redis/Celery background processing foundation
- Tool-only MCP service for ChatGPT reads and draft writes
- Docker Compose deployment for WSL2 and future server migration

## Windows trial — automated

فایل `INSTALL-PDP-ONE.bat` را با دسترسی Administrator اجرا کنید. نصب‌کننده، موتور کانتینر سازگار با Docker، Cloudflared و پیش‌نیازهای Windows/WSL2 را بررسی می‌کند، رمزهای تصادفی می‌سازد، داده آزمایشی مشخص ایجاد می‌کند و سرویس‌ها را بالا می‌آورد.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\Install-PDPOne.ps1
```

پس از نصب:

```powershell
# لینک موقت اینترنتی و اتصال خودکار تا مرحله تأیید ChatGPT
.\CONNECT-CHATGPT.bat

# کنترل سلامت
powershell -ExecutionPolicy Bypass -File .\scripts\windows\Test-PDPOne.ps1

# توقف بدون حذف داده‌ها
powershell -ExecutionPolicy Bypass -File .\scripts\windows\Stop-PDPOne.ps1
```

برای دریافت نسخه جدید بدون حذف تنظیمات و داده‌های موجود، آخرین ZIP مخزن را دریافت و فایل زیر را با دسترسی Administrator اجرا کنید:

به‌روزرسان پس از موفقیت، کش Build و ایمیج‌های بلااستفاده Docker و بسته‌های قدیمی PDP One در Downloads را پاک‌سازی می‌کند. پایگاه داده، فایل‌های خصوصی و Docker Volumeهای ماندگار حذف نمی‌شوند.

```text
UPDATE-PDP-ONE.bat
```

برای پاک‌سازی فوری فضای نسخه‌های قبلی، فایل زیر را با دسترسی Administrator اجرا کنید:

```text
CLEAN-PDP-ONE-DISK.bat
```

## Manual local trial

1. Copy `.env.example` to `.env` and replace all placeholder secrets.
2. Run `docker compose up --build -d` inside WSL2.
3. Open `http://localhost:8080`.
4. Create the first administrator with `docker compose exec backend python manage.py createsuperuser`.

Do not use the temporary trial link as a permanent production deployment. The random URL path and ephemeral HTTPS tunnel are suitable for the controlled trial only.

## ChatGPT connection

Double-click `CONNECT-CHATGPT.bat`. It starts or updates the services, verifies health, launches the official Tailscale container through the configured registry cache, creates a free temporary HTTPS Funnel, copies the tokenized MCP URL to the clipboard, opens the ChatGPT app settings and writes the exact connection fields to `PDP-ONE-CHATGPT-CONNECTION.txt`. On the first run only, complete the Tailscale account and Funnel approval pages opened by the script; the device identity is then preserved in a local Docker volume.

This integration does not use the OpenAI API; ChatGPT invokes the MCP tools from the user's ChatGPT workspace.

The connector can check system health, search contracts and receivables, return persisted management/finance summaries, and create contract, receivable, receipt and analysis drafts. Approval, deletion and financial finalization remain human-only actions.

No OpenAI API key is used. The unavoidable final action is confirming the custom app inside the authenticated ChatGPT Business workspace. See [docs/chatgpt-connection.md](docs/chatgpt-connection.md).
