from pathlib import Path

workspace = Path("app/procurement/ProcurementWorkspaceV13.tsx")
text = workspace.read_text(encoding="utf-8")

start_marker = "  const hasLoadedOnce = useRef(false);\n"
end_marker = "  const activeRun = extractionRuns.find((run) => run.status === \"queued\" || run.status === \"running\");\n"
start = text.index(start_marker)
end = text.index(end_marker, start)

replacement = '''  const hasLoadedOnce = useRef(false);
  const managementLoadVersion = useRef(-1);

  useEffect(() => {
    let active = true;
    async function load() {
      if (!hasLoadedOnce.current) setMode("loading");
      try {
        const sessionResponse = await fetch(`${API_BASE}/auth/session/`, { credentials: "include", headers: { Accept: "application/json" } });
        if (!sessionResponse.ok) throw new Error("session-unavailable");
        const session = await sessionResponse.json() as { authenticated?: boolean; username?: string | null };
        if (!session.authenticated) {
          if (active) {
            setUsername("");
            setMode("unauthorized");
          }
          return;
        }

        // Critical path: authenticate, load dashboard totals and only the first
        // page of operational records. This lets the workspace become usable
        // without waiting for every historical page or management-only dataset.
        const [noticeItems, directItems, dashboardResponse] = await Promise.all([
          fetchCollection<ApiNotice>(`${PROCUREMENT_API}/notices/?ordering=-last_seen_at`, 1),
          fetchCollection<ApiDirectOpportunity>(`${PROCUREMENT_API}/direct-opportunities/?ordering=-last_activity_at`, 1),
          fetch(`${PROCUREMENT_API}/dashboard/`, { credentials: "include", headers: { Accept: "application/json" } }),
        ]);
        if (dashboardResponse.status === 401 || dashboardResponse.status === 403) throw new Error("unauthorized");
        if (!dashboardResponse.ok) throw new Error(`dashboard-${dashboardResponse.status}`);
        const dashboardPayload = await dashboardResponse.json() as DashboardPayload;
        if (!active) return;

        setUsername(session.username || "");
        setNotices(noticeItems);
        setDirectReferrals(directItems);
        setDashboard(dashboardPayload);
        hasLoadedOnce.current = true;
        setMode("live");

        // Complete the operational collections in the background. A slow later
        // page must never cover or remove the already usable workspace.
        void Promise.all([
          fetchCollection<ApiNotice>(`${PROCUREMENT_API}/notices/?ordering=-last_seen_at`),
          fetchCollection<ApiDirectOpportunity>(`${PROCUREMENT_API}/direct-opportunities/?ordering=-last_activity_at`),
        ]).then(([allNotices, allDirectItems]) => {
          if (!active) return;
          setNotices(allNotices);
          setDirectReferrals(allDirectItems);
        }).catch(() => {
          if (active) setMessage("ادامه اطلاعات در پس‌زمینه موقتاً کامل نشد؛ اطلاعات اولیه قابل استفاده است.");
        });
      } catch (error) {
        if (!active) return;
        if (!hasLoadedOnce.current) {
          setMode(error instanceof Error && error.message === "unauthorized" ? "unauthorized" : "error");
        } else {
          setMessage("به‌روزرسانی پس‌زمینه موقتاً انجام نشد؛ داده‌های قبلی حفظ شدند.");
        }
      }
    }
    load();
    return () => { active = false; };
  }, [refresh]);

  // Sources, extraction history and automation settings are management-only
  // data. Fetch them lazily when that tab is opened instead of delaying every
  // visit to the dashboard, tenders or inquiries.
  useEffect(() => {
    if (tab !== "management" || mode !== "live" || managementLoadVersion.current === refresh) return;
    managementLoadVersion.current = refresh;
    let active = true;

    async function loadManagementData() {
      try {
        const [sourceItems, runItems, automationItems] = await Promise.all([
          fetchCollection<ApiSource>(`${PROCUREMENT_API}/sources/`),
          fetchCollection<ApiExtractionRun>(`${PROCUREMENT_API}/extraction-runs/?ordering=-created_at`),
          fetchCollection<ApiAutomationSettings>(`${PROCUREMENT_API}/automation-settings/`),
        ]);
        if (!active) return;
        const currentAutomation = automationItems[0] || null;
        setSources(sourceItems);
        setExtractionRuns(runItems);
        setAutomation(currentAutomation);
        if (currentAutomation) {
          setSchedule((current) => ({
            ...current,
            enabled: currentAutomation.enabled,
            cadence: currentAutomation.cadence,
            dailyTime: currentAutomation.daily_time?.slice(0,5) || "07:30",
            intervalHours: Math.max(1, Math.round(currentAutomation.interval_minutes / 60)),
          }));
        }
      } catch {
        if (!active) return;
        managementLoadVersion.current = -1;
        setMessage("اطلاعات مدیریت زیرسامانه موقتاً بارگذاری نشد؛ سایر بخش‌ها فعال‌اند.");
      }
    }

    loadManagementData();
    return () => { active = false; };
  }, [tab, mode, refresh]);

'''

text = text[:start] + replacement + text[end:]
workspace.write_text(text, encoding="utf-8")

compose = Path("docker-compose.yml")
compose_text = compose.read_text(encoding="utf-8")
old_build_id = "procurement-session-poll-v24-20260724"
new_build_id = "procurement-fast-initial-v25-20260725"
if compose_text.count(old_build_id) != 2:
    raise SystemExit(f"Expected two V24 build identifiers, found {compose_text.count(old_build_id)}")
compose.write_text(compose_text.replace(old_build_id, new_build_id), encoding="utf-8")

print("Applied V25 fast initial-load patch.")
