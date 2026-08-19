# راهنمای Deploy ایمن PDP One — lineage BACKLOG-001

> این سند با معماری فعلی به‌روزرسانی شده است. Repository برنامه `PDP-WEBBASE/PDP-One` عمومی است و Control/Memory خصوصی در `PDP-WEBBASE/PDP-One-Control` نگه‌داری می‌شود. مسیر عادی Deployment از Imageهای immutable در GHCR استفاده می‌کند و Local application-image build مسیر عادی نیست.

## مرزهای اعتماد

- Repository عمومی `PDP-WEBBASE/PDP-One` مرجع Canonical کد برنامه، Test، GitHub Actions و Commit/PR identity است؛ داده عملیاتی، Secretها و Canonical Project Memory در آن نگه‌داری نمی‌شوند.
- Repository خصوصی `PDP-WEBBASE/PDP-One-Control` مرجع Canonical حافظه پروژه، Sessionها، Governance و شواهد عملیاتی خصوصی است و نباید به Workflow عمومی Credential دسترسی به آن داده شود.
- ChatGPT از طریق MCP فقط درخواست enum/allowlisted می‌سازد. درخواست شامل payload امضاشده، nonce، زمان ایجاد و زمان انقضاست.
- Scheduled Task با حساب Windows مالک نصب و Highest Privileges اجرا می‌شود. عامل HMAC، expiry، replay marker، SHA دقیق و allowlist را دوباره بررسی می‌کند.
- هیچ ابزار عمومی Shell، PowerShell، CMD، SQL یا Docker در MCP وجود ندارد.

## اقدام اولیه یک‌باره

`INSTALL-PDP-ONE-DEPLOYMENT-AGENT.bat` را یک‌بار اجرا کنید. Setup یک GitHub Personal Access Token (classic) با حداقل Scope برابر `read:packages` می‌گیرد تا Deployment Agent بتواند Imageهای خصوصی PDP One را از `ghcr.io` Pull کند. حساب GitHub مربوط باید روی Packageهای Container مجوز Read داشته باشد. Repository برنامه Public است و برای خواندن Source عمومی Scope اضافی `repo` لازم نیست.

Installer قبل از ذخیره Credential، Login به GHCR را کنترل می‌کند. Credential فقط با DPAPI همان حساب Windows نگه‌داری می‌شود، ACL پوشه ProgramData محدود است و Token نمایش داده یا در `.env`، Git، ChatGPT، Screenshot یا Log نوشته نمی‌شود.

برای شکستن چرخه‌ی اولیه، Setup فقط Compose/MCP control plane امضاشده را با Backup و بازگشت محدود Bootstrap می‌کند؛ Web، داده، Volume، Tailscale identity، Migration و MCP path token را تغییر نمی‌دهد.

## جریان عادی Development-fast

1. تغییر روی Branch جداگانه ساخته می‌شود و Private Control Session/soft lock مربوط ثبت می‌شود.
2. Public Boundary، CI و در صورت نیاز Build immutable images روی exact PR head اجرا می‌شوند.
3. Imageهای backend/MCP/web با Tag مبتنی بر SHA کامل Commit در GHCR ساخته و Push می‌شوند؛ Local application-image build در مسیر عادی مجاز نیست.
4. PRE-DEPLOY Delta/Concurrency Sync باید `main`، PR head، Deployment Queue و Runtime مرتبط را دوباره کنترل کند.
5. Deployment Agent exact commit را از GitHub تأیید، با Credential محافظت‌شده به GHCR Login و همان Imageهای immutable را Pull می‌کند. Revision label هر Image باید با SHA مورد انتظار منطبق باشد.
6. Source همان SHA دریافت و Compose اعتبارسنجی می‌شود. اگر `release/database-change-risk.json` نیاز به Backup استاندارد را اعلام کند، development-fast متوقف و مسیر محافظت‌شده مناسب استفاده می‌شود.
7. در Development-fast عادی، سرویس‌ها با Imageهای immutable فعال، Migration کنترل‌شده اجرا و Health کوتاه محلی/PostgreSQL/عمومی بررسی می‌شود. حذف Volume، Prune داده و Rotation توکن جزو Deployment عادی نیست.
8. فقط بعد از exact deployment و Health پذیرفته‌شده، PR Merge می‌شود و lineage شامل PR head، Deployment ID، Image identity و Merge commit در Private Control ثبت می‌شود.

## قفل‌ها و Audit

- Queue امضاشده و کنترل concurrency از Deploy هم‌زمان جلوگیری می‌کند؛ Request تکراری/منقضی نباید به Retry کور تبدیل شود.
- هر nonce پس از اجرا marker دارد و Audit در `C:\ProgramData\PDP-One\deployment-agent\audit` بدون params حساس نگه‌داری می‌شود.
- گزارش Deployment در `C:\ProgramData\PDP-One\deployment-agent\reports` stage و نتیجه را ثبت می‌کند، اما Secret برنمی‌گرداند.
- Automatic rollback در Development-fast فعال نیست؛ در صورت شکست، ابتدا stage و `production_changed` بررسی و سپس recovery/rollback آگاهانه انجام می‌شود.

## Startup در برابر Deployment

`START-PDP-ONE.bat` برای بالا آوردن نصب موجود است و نباید به‌صورت خودکار Migration، Credential rotation، destructive volume operation یا Local application-image build انجام دهد. تغییر نسخه برنامه فقط از مسیر Governed exact-commit / immutable-image Deployment انجام می‌شود.
