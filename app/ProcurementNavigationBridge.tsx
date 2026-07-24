"use client";

import { useEffect } from "react";

export default function ProcurementNavigationBridge() {
  useEffect(() => {
    function routeProcurement(event: MouseEvent) {
      const target = event.target;
      if (!(target instanceof Element)) return;
      const button = target.closest(".sidebar nav button");
      if (!button || !button.textContent?.trim().startsWith("مناقصات و فرصت‌ها")) return;
      event.preventDefault();
      event.stopPropagation();
      window.location.assign("/procurement");
    }

    document.addEventListener("click", routeProcurement, true);
    return () => document.removeEventListener("click", routeProcurement, true);
  }, []);

  return null;
}
