import React, { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { api } from "../lib/apiClient";

/**
 * Site-wide maintenance mode banner. Visible when admin toggles maintenance_mode on.
 * Backend already blocks write endpoints while maintenance is active (503 response).
 */
export default function MaintenanceBanner() {
  const [s, setS] = useState(null);

  useEffect(() => {
    let alive = true;
    const load = () => api.get("/settings").then((r) => alive && setS(r.data)).catch(() => {});
    load();
    const t = setInterval(load, 60 * 1000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  if (!s?.maintenance_mode) return null;
  return (
    <div className="bg-amber-500 text-ink-inverted border-b-2 border-amber-600" data-testid="maintenance-banner" role="alert">
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-2 flex items-center gap-3 text-xs sm:text-sm">
        <AlertTriangle size={16} className="shrink-0" />
        <span className="flex-1">
          <strong>Режим на поддръжка: </strong>
          {s.maintenance_message || "Сайтът се обновява. Някои действия може да не работят."}
        </span>
      </div>
    </div>
  );
}
