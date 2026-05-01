import React from "react";

/**
 * Round avatar with graceful fallback to initials.
 * - `url`  : optional uploaded avatar URL (data URL or https URL).
 * - `name` : display name; first letter is shown when no avatar.
 * - `size` : pixel diameter (default 32).
 */
export default function Avatar({ url, name = "?", size = 32, className = "", testId }) {
  const initial = (name || "?").trim().charAt(0).toUpperCase() || "?";
  const px = Number(size);
  const fontSize = Math.max(11, Math.round(px * 0.42));

  if (url) {
    return (
      <img
        src={url}
        alt={name}
        loading="lazy"
        width={px}
        height={px}
        className={`rounded-full object-cover shrink-0 border border-[hsl(var(--line))] ${className}`}
        style={{ width: px, height: px }}
        data-testid={testId}
      />
    );
  }
  // Deterministic accent based on first character — keeps colors consistent
  // across renders for the same user without storing anything extra.
  const palette = [
    "hsl(var(--accent))",
    "#7C5CFF",
    "#E9A23B",
    "#3BB7E9",
    "#E94B6A",
    "#5BA66D",
  ];
  const bg = palette[initial.charCodeAt(0) % palette.length];

  return (
    <span
      className={`rounded-full inline-flex items-center justify-center shrink-0 text-white font-semibold ${className}`}
      style={{ width: px, height: px, fontSize, background: bg }}
      data-testid={testId}
      aria-label={name}
    >
      {initial}
    </span>
  );
}
