import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function source(path){return readFile(new URL(path,import.meta.url),"utf8");}

test("contract draft UI requires explicit confirmation and remains finance-free",async()=>{
 const panel=await source("../app/procurement/CaseContractDraftPanel.tsx");
 assert.match(panel,/cases\/\$\{selected\.id\}\/contract-draft\//);
 assert.match(panel,/confirmed:true/);
 assert.match(panel,/method:"POST"/);
 assert.match(panel,/فقط پیش‌نویس/);
 assert.doesNotMatch(panel,/receivables\//);
 assert.doesNotMatch(panel,/payment-receipts\//);
});

test("case follow-up UI uses live reminder and audit-backed endpoints",async()=>{
 const panel=await source("../app/procurement/CaseFollowUpPanel.tsx");
 assert.match(panel,/cases\/follow-up\/summary\//);
 assert.match(panel,/cases\/follow-up\/users\//);
 assert.match(panel,/cases\/\$\{selectedId\}\/follow-up\//);
 assert.match(panel,/X-CSRFToken/);
 assert.match(panel,/یادداشت‌های اخیر/);
 assert.doesNotMatch(panel,/mock/i);
});

test("management dashboard reads one live aggregate endpoint",async()=>{
 const panel=await source("../app/procurement/ManagementDashboardPanel.tsx");
 assert.match(panel,/procurement\/management-dashboard\//);
 assert.match(panel,/فقط داده واقعی سامانه/);
 assert.match(panel,/داده نمونه استفاده نشده است/);
 assert.doesNotMatch(panel,/const\s+sample/i);
});

test("automation control is explicit and draft-only",async()=>{
 const panel=await source("../app/procurement/AutomationControlPanel.tsx");
 assert.match(panel,/procurement\/automation-settings\//);
 assert.match(panel,/method:"PATCH"/);
 assert.match(panel,/X-CSRFToken/);
 assert.match(panel,/فقط به‌صورت Draft/);
 assert.match(panel,/مرکز بازبینی/);
 assert.doesNotMatch(panel,/publish/i);
});
