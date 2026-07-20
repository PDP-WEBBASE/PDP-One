# اتصال پایدار PDP One به ChatGPT Business

PDP One یک MCP server محدود دارد و به OpenAI API key نیاز ندارد. داده‌ها در PostgreSQL و Volumeهای خصوصی نصب باقی می‌مانند؛ ChatGPT فقط ابزارهای مشخص Read و Draft Write را فراخوانی می‌کند.

## اتصال نخست

1. `CONNECT-CHATGPT.bat` را با Administrator اجرا کنید.
2. در اولین بار، ورود Tailscale و تأیید Funnel را در Browser کامل کنید.
3. URL خصوصی فقط در Clipboard و فایل محلی `PDP-ONE-CHATGPT-CONNECTION.txt` قرار می‌گیرد و در Console چاپ نمی‌شود.
4. App سفارشی ChatGPT را با `No Authentication` ایجاد و ابزارها را Scan/Save کنید.

پس از این مرحله، هویت Tailscale و `PDP_MCP_PATH_TOKEN` حفظ می‌شوند. Restart عادی Windows، Startup، Update و Recovery توکن را تغییر نمی‌دهند و App به ویرایش روزانه نیاز ندارد.

## Rotation

Rotation از Startup جداست. فقط `ROTATE-PDP-ONE-MCP-TOKEN.bat` یا ابزار تأییدشده `rotate_mcp_token` می‌تواند آن را انجام دهد. Rotation از `.env` نسخه DPAPI می‌گیرد، Nginx را به‌تنهایی بازسازی می‌کند، Health را می‌سنجد و در شکست توکن قبلی را برمی‌گرداند. فقط پس از Rotation باید URL App یک‌بار به‌روز شود.

## ابزارها

ابزارهای داده‌ای قرارداد، مطالبات، خلاصه‌ها و ایجاد Draft حفظ شده‌اند. ابزارهای Deployment فقط درخواست‌های allowlist را در صف محلی امضاشده قرار می‌دهند: status، approval، backup، restore verification، deploy، health، rollback و rotation. تأیید/حذف رکوردهای کسب‌وکار و قطعی‌سازی مالی همچنان انسانی است.

## آزمون اتصال

در ChatGPT اجرا کنید:

```text
با PDP One وضعیت سیستم را بررسی کن و تعداد قراردادها و مطالبات را گزارش بده.
```

نتیجه باید `database: connected` را برگرداند. مقدار URL خصوصی، Token یا Authorization header را در Screenshot، Log یا Chat منتشر نکنید.
