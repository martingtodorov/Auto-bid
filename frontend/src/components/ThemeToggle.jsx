import React, { useEffect, useState } from "react";
import { Sun, Moon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { getStoredTheme, setTheme } from "../lib/theme";

/** Three-state theme toggle (light → dark → system → light…). */
export default function ThemeToggle({ className = "" }) {
  const { t } = useTranslation();
  const [theme, setLocal] = useState(() => getStoredTheme());

  useEffect(() => {
    const onChange = (e) => setLocal(e.detail?.theme || getStoredTheme());
    window.addEventListener("ab:theme-changed", onChange);
    return () => window.removeEventListener("ab:theme-changed", onChange);
  }, []);

  const next = theme === "dark" ? "light" : "dark";
  const Icon = theme === "dark" ? Moon : Sun;
  const label =
    theme === "dark"
      ? t("theme.dark", "Тъмна тема")
      : t("theme.light", "Светла тема");

  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      title={label}
      aria-label={label}
      data-testid="theme-toggle"
      className={
        "inline-flex items-center justify-center w-9 h-9 rounded-full border border-[hsl(var(--line))] " +
        "hover:bg-[hsl(var(--surface))] transition-colors " +
        className
      }
    >
      <Icon size={16} />
    </button>
  );
}
