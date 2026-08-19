# بازیابی کامل PDP One پس از نصب مجدد Windows

## هدف

این مسیر برای خرابی کامل دیسک، حذف Rancher Desktop/WSL2 یا نصب مجدد Windows است. GitHub فقط Source و Migration را نگه می‌دارد؛ داده عملیاتی و Secretها فقط از فایل رمز‌شده `.pdpone` بازمی‌گردند.

## ساخت Backup قابل‌انتقال

1. یک دیسک خارجی یا مسیر شبکه با فضای کافی متصل کنید.
2. `CREATE-PDP-ONE-PORTABLE-BACKUP.bat` را با دسترسی Administrator اجرا کنید.
3. مسیر خارج از درایو Windows را وارد کنید.
4. یک Passphrase حداقل ۱۴ کاراکتری را دوبار وارد کنید.
5. ابزار پس از کنترل SHA-256، یک نسخه را در مسیر خارجی انتخاب‌شده و نسخه‌ای یکسان را به‌صورت خودکار در `D:\BackUp PDP-0NE-14050429-01` ذخیره می‌کند.
6. گزارش امن `PDP-ONE-PORTABLE-BACKUP-REPORT.json` را کنترل و حداقل یک نسخه `.pdpone` را خارج از کامپیوتر نگه‌داری کنید.

اگر هر مرحله شکست بخورد، همان گزارش Desktop شامل `failed_step` و خطای پاک‌سازی‌شده خواهد بود. داده‌ها و Backupهای قبلی حذف نمی‌شوند و هر کپی خروجی فقط پس از تطبیق SHA-256 نهایی می‌شود.

قبل از رمزگذاری، PostgreSQL در Container جداگانه Restore، Archiveها و Hashها کنترل و Snapshot کد تهیه می‌شود. فایل نهایی با AES-256-CBC رمز و با HMAC-SHA256 احراز اصالت می‌شود. PBKDF2-HMAC-SHA256 با Salt تصادفی کلیدها را از Passphrase مشتق می‌کند.

## Restore روی Windows تمیز

1. Source یا ZIP همان Release ثابت GitHub را Extract کنید.
2. فایل `.pdpone` را کنار `RESTORE-PDP-ONE.bat` بگذارید؛ یا هنگام اجرا مسیر کامل آن را وارد کنید.
3. `RESTORE-PDP-ONE.bat` را اجرا و Passphrase را وارد کنید.
4. ابزار، Source ثبت‌شده در Backup را در `C:\PDP-One` بازسازی، پیش‌نیازها را نصب، `.env`، PostgreSQL، فایل‌های خصوصی، Redis و هویت Tailscale را Restore و Health را اجرا می‌کند.
5. هنگام نصب Deployment Agent، یک GitHub Personal Access Token (classic) با حداقل Scope برابر `read:packages` و متعلق به حسابی که مجوز Read روی Packageهای Container خصوصی PDP One دارد وارد کنید. Repository برنامه Public است و برای Source عمومی Scope اضافی `repo` لازم نیست. Token فقط در همان Windows account با DPAPI نگه‌داری می‌شود و نباید در GitHub، Backup، ChatGPT، Screenshot یا Log قرار گیرد.

اگر Windows برای WSL یا VirtualMachinePlatform نیازمند Restart باشد، پس از ورود مجدد همان `RESTORE-PDP-ONE.bat` را اجرا کنید. Marker امن فقط اجازه ادامه همان Backup را می‌دهد و از بازنویسی مسیر نامرتبط جلوگیری می‌کند.

## محدودیت‌های امنیتی

- Passphrase قابل بازیابی از فایل یا GitHub نیست.
- Backup را روی همان درایو Windows نگه ندارید.
- Restore هیچ Volume موجود یا پوشه نصب غیرخالیِ نامرتبط را حدس‌زده و بازنویسی نمی‌کند.
- تغییر یا خرابی حتی یک بایت فایل با HMAC شناسایی و Restore متوقف می‌شود.
- اتصال ChatGPT فقط پس از Restore هویت Tailscale و MCP path token بررسی می‌شود.
