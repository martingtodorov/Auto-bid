import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { setPageMeta, resetPageMeta, buildBreadcrumbs } from "./seo";

/**
 * Apply meta + breadcrumb JSON-LD to a static info page.
 * Call inside a component:
 *   useInfoPageSeo({ title, description, path: "/faq", crumb: "FAQ" });
 *
 * `crumb` is the localized name for the last breadcrumb segment. The
 * "Home" segment is translated automatically from i18n.
 */
export function useInfoPageSeo({ title, description, path, crumb }) {
  const { t, i18n } = useTranslation();
  useEffect(() => {
    const origin = typeof window !== "undefined" ? window.location.origin : "";
    const url = origin + path;
    const homeName = t("page_meta.home_crumb", "Home");
    const jsonLd = buildBreadcrumbs([
      { name: homeName, url: origin + "/" },
      { name: crumb, url },
    ]);
    const lang = (i18n.resolvedLanguage || i18n.language || "bg").slice(0, 2);
    setPageMeta({ title, description, url, jsonLd, locale: lang });
    return () => resetPageMeta();
    // eslint-disable-next-line
  }, [title, description, path, crumb, i18n.language, i18n.resolvedLanguage]);
}
