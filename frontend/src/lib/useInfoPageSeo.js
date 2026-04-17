import { useEffect } from "react";
import { setPageMeta, resetPageMeta, buildBreadcrumbs } from "./seo";

/**
 * Apply meta + breadcrumb JSON-LD to a static info page.
 * Call inside a component:
 *   useInfoPageSeo({ title, description, path: "/faq", crumb: "FAQ" });
 */
export function useInfoPageSeo({ title, description, path, crumb }) {
  useEffect(() => {
    const origin = typeof window !== "undefined" ? window.location.origin : "";
    const url = origin + path;
    const jsonLd = buildBreadcrumbs([
      { name: "Начало", url: origin + "/" },
      { name: crumb, url },
    ]);
    setPageMeta({ title, description, url, jsonLd });
    return () => resetPageMeta();
    // eslint-disable-next-line
  }, [title, description, path, crumb]);
}
