# PDP One

سامانه یکپارچه مدیریت پروژه، قرارداد، مناقصه، مطالبات و تحلیل مدیریتی با رابط فارسی RTL، Django/PostgreSQL، Celery/Redis و اتصال محدود MCP به ChatGPT.

## اجرای پایدار Windows

پس از نصب اولیه، عملیات روزمره از هم تفکیک شده‌اند:

- `START-PDP-ONE.bat`: فقط Rancher، سرویس‌های موجود، Tailscale Funnel و Health Check را اجرا می‌کند. این مسیر Build، Pull، Migration یا Rotation ندارد.
- `STOP-PDP-ONE.bat`: سرویس‌ها را بدون حذف Volume، هویت Tailscale یا تنظیمات متوقف می‌کند.
- `CONNECT-CHATGPT.bat`: اتصال یک‌باره App را آماده می‌کند و توکن موجود را حفظ می‌کند.
- `ROTATE-PDP-ONE-MCP-TOKEN.bat`: مسیر مستقل و تأییدشده برای Rotation؛ تنها عملیاتی است که نیازمند ویرایش دوباره URL در App است.
- `UPDATE-PDP-ONE.bat`: مسیر اضطراری دستی است. مسیر عادی Deploy پس از Preview و تأیید، توسط عامل محلی انجام می‌شود.

نصب اولیه:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\Install-PDPOne.ps1
```

بازیابی پس از نصب مجدد کامل Windows:

1. روی سیستم سالم، `CREATE-PDP-ONE-PORTABLE-BACKUP.bat` را اجرا کنید؛ فایل رمز‌شده `.pdpone` هم در مقصد خارجی انتخابی و هم در `D:\BackUp PDP-0NE-14050429-01` ذخیره و با SHA-256 کنترل می‌شود.
2. روی Windows جدید، Source همین Release و فایل `.pdpone` را در دسترس قرار دهید.
3. `RESTORE-PDP-ONE.bat` را اجرا کنید. اگر فعال‌سازی WSL نیازمند Restart بود، پس از ورود مجدد همان BAT را دوباره اجرا کنید.

Passphrase در GitHub، گزارش یا Backup ذخیره نمی‌شود و بدون آن Restore ممکن نیست.

راه‌اندازی عامل محلی یک اقدام یک‌باره است:

```text
INSTALL-PDP-ONE-DEPLOYMENT-AGENT.bat
```

عامل فقط صف محلی HMAC-signed، فرمان‌های allowlist، SHA دقیق Commit و تأیید منقضی‌شونده را می‌پذیرد. اجرای عمومی PowerShell/CMD در ابزارهای MCP وجود ندارد.

## جریان تغییر و استقرار

```text
Branch → Tests/Security → Preview → توقف برای تأیید صریح
→ Backup نهایی و Restore آزمایشی → Deploy Commit قفل‌شده
→ Health چندلایه → گزارش یا Rollback خودکار
```

نمایش Preview هرگز مجوز Deploy نیست. `.env`، داده PostgreSQL، فایل‌های خصوصی، Redis و هویت Tailscale در Git ذخیره نمی‌شوند و Volumeها در Startup/Update حذف نمی‌شوند.

## اسناد عملیاتی

- [معماری](docs/architecture.md)
- [اتصال پایدار ChatGPT](docs/chatgpt-connection.md)
- [راهنمای Deploy و عامل محلی](docs/backlog-001-deployment.md)
- [راهنمای بازیابی و Rollback](docs/recovery.md)
- [وضعیت BACKLOG-001](docs/backlog-001-status.md)
- [Backup قابل‌انتقال و بازیابی کامل Windows](docs/bare-metal-recovery.md)
