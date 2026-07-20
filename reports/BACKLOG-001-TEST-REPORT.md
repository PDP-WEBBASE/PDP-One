# BACKLOG-001 — Test report

وضعیت: اجرای تست Branch؛ آزمون‌های Windows/Production تا بعد از Preview و تأیید اجرا نمی‌شوند.

| آزمون | وضعیت | توضیح |
|---|---|---|
| Python compile | passed | backend و MCP |
| Signed queue unit tests | passed | allowlist، exact SHA، HMAC، عدم نشت signing key و جلوگیری از path traversal |
| Secret pattern scan | passed | PAT/OpenAI/Tailscale token pattern یافت نشد |
| Forbidden destructive command scan | passed | down -v، volume rm و prune --volumes یافت نشد |
| Web build/test/lint | passed | Vinext build، artifact validation، rendered HTML test و ESLint |
| Django migrations | passed | `makemigrations --check --dry-run` بدون تغییر |
| Django tests | passed | 13/13 شامل Draft-only، Audit، Finance، Session و Seed idempotency |
| PowerShell parser | pending CI | Windows PowerShell در محیط Scratch حاضر نیست؛ CI با `pwsh` ParseFile اجرا می‌کند |
| Backup/restore واقعی Windows | passed for initial backup | گزارش مستقل کاربر تأیید شد |
| Restart/Deploy failure/Rotation واقعی | blocked until approval | اجرای Production پیش از Preview ممنوع است |
