import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";
import { bootTheme } from "@/lib/theme";

bootTheme();

// ── Block iOS Safari pinch-zoom + double-tap-zoom ──────────────────────────
// The viewport `user-scalable=no` meta alone is ignored by modern iOS Safari.
// Listening for `gesturestart` + a double-tap watchdog brings the behaviour
// in line with Android Chrome (which respects the meta). Passive listeners
// keep scroll performance untouched.
if (typeof window !== "undefined") {
  document.addEventListener("gesturestart", (e) => e.preventDefault());
  document.addEventListener("gesturechange", (e) => e.preventDefault());
  document.addEventListener("gestureend", (e) => e.preventDefault());

  let lastTouchEnd = 0;
  document.addEventListener(
    "touchend",
    (e) => {
      const now = Date.now();
      if (now - lastTouchEnd <= 350) {
        e.preventDefault();
      }
      lastTouchEnd = now;
    },
    { passive: false }
  );
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
