import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { setPageMeta, resetPageMeta } from "./seo";

/**
 * Apply localised <title> + meta description to a private (auth-gated)
 * page. Marked `noindex, nofollow` so private surfaces never leak into
 * Google. No breadcrumb JSON-LD — these pages are not indexable.
 *
 * Usage:
 *   usePrivatePageMeta({ titleKey: "page_meta.dashboard_title",
 *                        descKey:  "page_meta.dashboard_desc",
 *                        brand });
 */
export function usePrivatePageMeta({ titleKey, descKey, brand }) {
  const { t, i18n } = useTranslation();
  useEffect(() => {
    const lang = (i18n.resolvedLanguage || i18n.language || "bg").slice(0, 2);
    setPageMeta({
      title: t(titleKey, { brand }),
      description: t(descKey, { brand }),
      url: typeof window !== "undefined" ? window.location.href : "",
      locale: lang,
      robots: "noindex, nofollow",
    });
    return () => resetPageMeta();
  }, [titleKey, descKey, brand, t, i18n.language, i18n.resolvedLanguage]);
}
