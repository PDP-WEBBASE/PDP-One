# PDP One Stable Release v1

## هدف

این سند مسیر انتقال کنترل‌شده MVP از حالت آزمایشی سریع به Release پایدار را ثبت می‌کند.

## گیت انتقال

انتقال فقط پس از موفقیت همه موارد زیر انجام می‌شود:

1. CI کامل Commit دقیق.
2. استقرار Commit در `development_fast` برای نصب ابزار Release.
3. Backup نهایی متصل به همان Commit و Deployment ID.
4. Restore Verification در PostgreSQL ایزوله.
5. بررسی صحت آرشیو فایل‌های خصوصی، Redis و Tailscale.
6. Mirror و SHA-256 verification در مسیر خارجی مصوب.
7. فعال‌سازی `PDP_CHANGE_MANAGEMENT_MODE=standard` و `PDP_TRIAL_MODE=false`.
8. Restart کنترل‌شده سرویس‌ها و Health محلی/عمومی.
9. ثبت مجدد Startup Taskهای Windows.
10. استقرار دوباره همان Commit از مسیر استاندارد با Approval و Backup تأییدشده.

## مسیر Backup خارجی

`D:\BackUp PDP-0NE-14050429-01`

Backup پایدار زمانی معتبر است که `backup-report.json` این موارد را تأیید کند:

- `restore_verified: true`
- `external_backup_copied: true`
- `standard_mode_activated: true`
- Commit و Deployment ID مطابق Release
- هش‌های اعضای Backup محلی و خارجی برابر

## Rollback

- اگر Backup یا Restore شکست بخورد، حالت استاندارد فعال نمی‌شود.
- اگر Restart یا Health پس از تغییر تنظیمات شکست بخورد، مقادیر قبلی `.env` بازگردانده و سرویس‌ها با تنظیمات قبلی Restart می‌شوند.
- Docker Volumeها حذف یا Prune نمی‌شوند.
- تغییر پایگاه داده فقط در استقرار استاندارد و با Backup تأییدشده قابل Rollback است.

## Startup و دسترسی عمومی

پس از فعال‌سازی Standard Mode:

- `Register-PDPOneStartupTask.ps1` دوباره اجرا می‌شود.
- Health محلی و مسیر عمومی ثابت بررسی می‌شوند.
- Tokenهای MCP و Tailscale تغییر نمی‌کنند.

## مدیریت تغییرات بعد از Release

هر تغییر بعدی باید از مسیر زیر عبور کند:

`Branch → CI → Preview → Approval دقیق → Backup نهایی → Restore Verification → Deploy → Health → Merge/Release`
