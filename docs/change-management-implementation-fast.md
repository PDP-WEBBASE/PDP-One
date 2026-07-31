# مدیریت تغییرات در دوره پیاده‌سازی PDP One

## وضعیت فعال

تا زمانی که مالک سامانه دقیقاً اعلام نکرده باشد:

`پیاده سازی سامانه تکمیل شده است`

سامانه در حالت `development_fast` و `trial_mode=true` باقی می‌ماند.

## گردش کار هر تغییر

`Branch → CI → Deploy exact commit → short health check → Merge`

## کنترل‌های باقی‌مانده

- Branch مستقل برای هر تغییر
- CI، تست‌های Frontend و Backend و کنترل Migration
- بررسی Secret و ممنوعیت عملیات مخرب Docker Volume
- دریافت و Deploy همان Commit دقیق GitHub
- Build تصاویر Candidate پیش از توقف سرویس فعال
- Health کوتاه محلی، PostgreSQL و مسیر عمومی
- Audit درخواست و استقرار
- ثبت Commit قبلی در وضعیت Agent و حفظ آن در GitHub

## کنترل‌های موقتاً حذف‌شده

- Approval جداگانه برای هر Deploy
- Backup پایگاه داده برای هر تغییر معمولی
- Restore Verification برای هر تغییر معمولی
- Snapshot محلی کد پیش از Deploy
- Rollback خودکار در هر استقرار
- Preview Gate سنگین
- Health و انتظارهای طولانی Agent

گزارش استقرار سریع باید صراحتاً این مقادیر را ثبت کند:

- `database_backup_created: false`
- `restore_verification_run: false`
- `local_code_snapshot_created: false`
- `automatic_rollback_enabled: false`

## بازگشت اضطراری

در صورت خرابی، Commit قبلی ثبت‌شده در GitHub با همان مسیر توسعه سریع دوباره Deploy می‌شود. این روش Rollback محلی خودکار نیست و به Snapshot ویندوز وابسته نمی‌ماند.

## تغییرات پایگاه داده

تغییرات معمول و Migrationهای افزایشی پس از CI و کنترل Migration در مسیر سریع اجرا می‌شوند.

برای هر Migration مخرب یا تغییر حساس پایگاه داده باید فایل زیر در Commit وجود داشته باشد:

`release/database-change-risk.json`

با محتوای حداقل:

```json
{
  "requires_backup": true,
  "reason": "شرح ریسک داده‌ای"
}
```

وجود این نشانگر Deploy سریع را متوقف می‌کند و تغییر باید از مسیر استاندارد دارای Backup و Restore Verification اجرا شود.

## پایان دوره پیاده‌سازی

فقط پس از عبارت صریح مالک، نشانگر `release/implementation-in-progress.json` در یک PR مستقل به وضعیت تکمیل تغییر می‌کند. سپس Issue شماره ۳۶ برای استانداردسازی، Release ثابت، آزمون Backup/Restore و Startup نهایی اجرا خواهد شد.
