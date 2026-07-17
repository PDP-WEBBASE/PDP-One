# PDP One

نسخه پایه سامانه یکپارچه مدیریت پروژه، قرارداد، مناقصات و تحلیل‌های مدیریتی.

## Current milestone

- Persian RTL responsive dashboard and PWA manifest
- Contract, project, tender, and analysis demonstration flows
- Django REST API foundation with PostgreSQL models
- Redis/Celery background processing foundation
- Tool-only MCP service for ChatGPT reads and draft writes
- Docker Compose deployment for WSL2 and future server migration

## Windows trial — automated

PowerShell را در پوشه پروژه باز کنید و اجرا کنید:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\Install-PDPOne.ps1
```

این اسکریپت Git، Docker Desktop و Cloudflared را در صورت نیاز با Winget نصب می‌کند، رمزهای تصادفی می‌سازد، کانتینرها را بالا می‌آورد و مدیر اولیه را ایجاد می‌کند.

پس از نصب:

```powershell
# لینک موقت اینترنتی
powershell -ExecutionPolicy Bypass -File .\scripts\windows\Start-PDPOneTunnel.ps1

# کنترل سلامت
powershell -ExecutionPolicy Bypass -File .\scripts\windows\Test-PDPOne.ps1

# توقف بدون حذف داده‌ها
powershell -ExecutionPolicy Bypass -File .\scripts\windows\Stop-PDPOne.ps1
```

## Manual local trial

1. Copy `.env.example` to `.env` and replace all placeholder secrets.
2. Run `docker compose up --build -d` inside WSL2.
3. Open `http://localhost:8080`.
4. Create the first administrator with `docker compose exec backend python manage.py createsuperuser`.

Do not expose the trial to the internet until passwords, allowed hosts, HTTPS, backup destination, and test-only data are confirmed.

## ChatGPT connection

The MCP endpoint is `/mcp`. It exposes read tools separately from draft-creation tools. For an internet-connected ChatGPT developer-mode test, expose Nginx through a temporary HTTPS tunnel and use the resulting URL plus `/mcp`.

This integration does not use the OpenAI API; ChatGPT invokes the MCP tools from the user's ChatGPT workspace.
