# بازیابی و Rollback PDP One

## موارد ممنوع

برای Recovery از `docker compose down -v`، حذف Volume، `docker system prune --volumes`، Factory Reset، حذف `C:\PDP-One` یا بازنویسی دستی `.env` استفاده نکنید.

## Backup

`New-PDPOneBackup.ps1` شامل Dump سفارشی PostgreSQL، `private_files`، وضعیت Tailscale، `.env` محافظت‌شده با DPAPI، Compose، نام Volumeها و SHA-256 فایل‌هاست. `Test-PDPOneBackupRestore.ps1` Hashها را کنترل، DB را در Container PostgreSQL مجزا Restore و Archiveها را بازخوانی می‌کند.

Backup نهایی باید `restore_verified: true` و Commit/Deployment یکسان با Release تأییدشده داشته باشد. Updater بدون این وضعیت اجرا نمی‌شود.

## Rollback خودکار

Updater پیش از کپی Source، Snapshot کد نگه می‌دارد. اگر Build، Migration، Startup، Health عمومی/MCP، شمارش داده یا continuity توکن شکست بخورد:

1. سرویس‌های Application متوقف می‌شوند؛ Volumeها حذف نمی‌شوند.
2. کد قبلی بازمی‌گردد.
3. اگر Migration شروع شده باشد، DB و فایل‌های سازگار از Backup verified بازگردانده می‌شوند.
4. سرویس نسخه قبل بالا می‌آید و Health کامل دوباره اجرا می‌شود.
5. نتیجه Rollback و Diagnostics redacted ثبت می‌شود.

Restore دستی فقط با `-Confirmed` و Restore عامل فقط با `-AutomaticRollback` مجاز است. Backup را پیش از هر Restore دوباره verify کنید.

## Diagnostics

`New-PDPOneDiagnostics.ps1` نسخه Windows/Docker، وضعیت Compose، سرویس خطادار، شناسه Backup/Deploy و Log محدود را ثبت می‌کند. Tokenها، Database URL/password، Authorization، PAT، Tailscale key و مسیر خصوصی MCP Mask می‌شوند.
