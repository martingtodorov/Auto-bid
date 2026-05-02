import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";
import { bootTheme } from "@/lib/theme";

bootTheme();

// ── Block iOS Safari pinch-zoom + double-tap-zoom ──────────────────────────
// The viewport `user-scalable=no` meta alone is ignored by modern iOS Safari.
// Listening for `gesturestart` + a double-tap watchdog brings the behaviour
// in line with Android Chrome (which respects the meta).
//
// Opt-out: any element (or ancestor) carrying `data-allow-pinch-zoom="1"`
// bypasses the block. The photo lightbox uses this so users CAN pinch-zoom
// listing photos while the surrounding app UI stays unzoomable.
if (typeof window !== "undefined") {
  const allowsPinch = (target) => {
    let el = target;
    while (el && el.nodeType === 1) {
      if (el.dataset && el.dataset.allowPinchZoom === "1") return true;
      el = el.parentElement;
    }
    return false;
  };

  const blockGesture = (e) => {
    if (!allowsPinch(e.target)) e.preventDefault();
  };
  document.addEventListener("gesturestart", blockGesture);
  document.addEventListener("gesturechange", blockGesture);
  document.addEventListener("gestureend", blockGesture);

  let lastTouchEnd = 0;
  document.addEventListener(
    "touchend",
    (e) => {
      const now = Date.now();
      if (now - lastTouchEnd <= 350 && !allowsPinch(e.target)) {
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
