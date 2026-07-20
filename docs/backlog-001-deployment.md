# راهنمای Deploy ایمن BACKLOG-001

## مرزهای اعتماد

- GitHub خصوصی `PDP-WEBBASE/PDP-One` مرجع Source و Migration است؛ داده عملیاتی هرگز در Git نیست.
- ChatGPT از طریق MCP فقط درخواست enum می‌سازد. درخواست شامل payload Base64، HMAC-SHA256، nonce، زمان ایجاد و زمان انقضاست.
- Scheduled Task با حساب Windows مالک نصب و Highest Privileges اجرا می‌شود. عامل HMAC، expiry، replay marker، SHA دقیق و allowlist را دوباره بررسی می‌کند.
- هیچ ابزار عمومی Shell، PowerShell، CMD، SQL یا Docker در MCP وجود ندارد.

## اقدام اولیه یک‌باره

`INSTALL-PDP-ONE-DEPLOYMENT-AGENT.bat` را یک‌بار اجرا کنید. Setup یک Fine-grained GitHub token با دسترسی فقط Read به Repository می‌گیرد، آن را با DPAPI همان حساب Windows نگه می‌دارد، ACL پوشه ProgramData را محدود و Scheduled Task را ثبت می‌کند. برای شکستن چرخه‌ی اولیه، فقط Compose/MCP control plane امضاشده را با Backup و بازگشت خودکار Bootstrap می‌کند؛ Web، داده، Volume، Tailscale identity، Migration و MCP path token را تغییر نمی‌دهد. Token نمایش داده یا در `.env`/Git نوشته نمی‌شود.

## جریان عادی پس از آن

1. تغییر روی Branch جداگانه ساخته و تست می‌شود.
2. Preview و شناسه Commit دقیق نمایش داده می‌شود و جریان متوقف می‌ماند.
3. پس از عبارت تأیید صریح، عامل همان Commit و Preview را حداکثر برای ۲۴ ساعت قفل می‌کند.
4. عامل دقیقاً پس از تأیید، Dump کامل PostgreSQL، فایل‌های خصوصی، `.env` رمز‌شده، وضعیت Tailscale/Volumeها و Snapshot کد را تهیه می‌کند.
5. Backup در PostgreSQL مجزا Restore و Archiveها/Hashها کنترل می‌شوند. شکست این گام Deploy را قبل از هر تغییر متوقف می‌کند.
6. Source همان SHA از GitHub دانلود، Images ساخته و Migration با `--noinput` اجرا می‌شود.
7. سرویس‌ها بدون حذف Volume بالا می‌آیند و Health چندلایه، شمارش داده و continuity توکن بررسی می‌شود.
8. در هر شکست، Snapshot کد و در صورت اجرای Migration، Backup سازگار DB/فایل/تنظیمات بازگردانده می‌شود.

## قفل‌ها و Audit

- Mutex سراسری از Deploy هم‌زمان جلوگیری می‌کند.
- هر nonce پس از اجرا marker دارد؛ درخواست منقضی یا تکراری رد می‌شود.
- Audit در `C:\ProgramData\PDP-One\deployment-agent\audit` بدون params حساس نگه‌داری می‌شود.
- پاسخ‌ها فقط status، شناسه‌ها و نتیجه Health/Backup را دارند؛ Secret بازگردانده نمی‌شود.

## Startup در برابر Update

`START-PDP-ONE.bat` از `docker compose up --no-build` استفاده می‌کند و هیچ Migration، Pull، Build یا Rotation ندارد. Migration فقط در Updater محافظت‌شده و بعد از Backup نهایی verified اجرا می‌شود.
