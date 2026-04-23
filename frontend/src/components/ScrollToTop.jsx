import { useEffect } from "react";
import { useLocation } from "react-router-dom";

/**
 * Scrolls to the top of the page whenever the route pathname changes. Keeps
 * hash-fragment links (`#section`) working normally by only scrolling on
 * fresh pathname navigation.
 */
export default function ScrollToTop() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    if (hash) {
      // Defer to next tick so the destination component has mounted
      const t = setTimeout(() => {
        const el = document.querySelector(hash);
        if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 100);
      return () => clearTimeout(t);
    }
    try { window.scrollTo({ top: 0, left: 0, behavior: "auto" }); } catch { window.scrollTo(0, 0); }
  }, [pathname, hash]);
  return null;
}
