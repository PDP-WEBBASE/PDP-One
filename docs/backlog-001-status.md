# وضعیت BACKLOG-001

وضعیت این سند: BACKLOG-001 روی Commit تأییدشده Deploy و Health نهایی آن موفق شده است. این سند همراه قابلیت بازیابی کامل برای ادغام در `main` آماده شده است.

## ممیزی مرجع

- Repository: `PDP-WEBBASE/PDP-One` (private)
- Main baseline: `527ec7b5613b844f810a3ab38221aa4665ca359b`
- Branch: `feature/backlog-001-stable-automated-deployment`
- نصب: `C:\PDP-One`
- Docker services: db، redis، backend، worker، beat، mcp، web، nginx و tailscale profile
- Volumeهای واقعی: `pdp-one_postgres_data`، `pdp-one_private_files`، `pdp-one_redis_data` و `pdp-one_tailscale_state`
- Local URL: `http://localhost:8080`
- Tailscale: `pdp-one-trial.tail84ea7e.ts.net`
- Connector ممیزی‌شده: v18؛ علت ریشه‌ای تغییر URL تولید اجباری `PDP_MCP_PATH_TOKEN` در هر اجرا بود.

## Backup اولیه معتبر

`PDP-One-Initial-Backup-20260720-154624` در ۲۰ ژوئیه ۲۰۲۶ ایجاد شد. PostgreSQL در محیط مجزا Restore شد (۴۱ Migration و ۸ Contract)، Archive فایل خصوصی و Tailscale بررسی، `.env` و state رمزگذاری و Health محلی/API/عمومی HTTP 200 ثبت شد. گزارش تأیید می‌کند Production تغییر نکرد، Deploy انجام نشد، Token نچرخید و Secret در گزارش نیست.

## وضعیت دروازه‌ها

- Audit و Gap analysis: انجام‌شده
- Backup اولیه و Restore verification: انجام‌شده
- Branch جداگانه: انجام‌شده
- کد Startup/Token/Agent/Backup/Updater/Rollback: Deploy شده
- تست‌های مستقل کد و Security: موفق برای Release تأییدشده
- Preview و تأیید صریح: انجام‌شده
- اقدام اولیه یک‌باره Agent: انجام‌شده
- Backup نهایی، Restore ایزوله، Deploy و Health نهایی: انجام‌شده
- Repairهای Health Gate 1.1 و Approval Gate 1.2.1: در Source پایدار ادغام شده‌اند
- Backup رمز‌شده قابل‌انتقال و Restore یک‌مرحله‌ای: برای Release ثابت اضافه شده‌اند
