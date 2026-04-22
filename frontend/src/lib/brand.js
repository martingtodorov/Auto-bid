import { useTranslation } from "react-i18next";
import { brandNameForLang } from "../i18n";

/**
 * React hook that returns the user-facing brand name (with language-specific
 * TLD suffix) for the currently active i18n language.
 *
 * Examples: "Auto&Bid.bg" / "Auto&Bid.ro" / "Auto&Bid.com"
 */
export function useBrandName() {
  const { i18n } = useTranslation();
  return brandNameForLang(i18n.resolvedLanguage || i18n.language);
}
