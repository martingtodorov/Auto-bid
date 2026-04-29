import React from "react";
import DOMPurify from "dompurify";

/**
 * Безопасен рендер на user/admin-управляван HTML.
 * - Премахва <script>, on* event handlers, javascript: URLs и SVG ескейпи.
 * - Запазва типография: h1-h6, p, span, em/i/strong/b, ul/ol/li, blockquote,
 *   a (target/rel forced), img (само https), table.
 * - Стилове и class атрибути са разрешени, за да може админ да форматира.
 */
const ALLOWED_TAGS = [
  "h1", "h2", "h3", "h4", "h5", "h6",
  "p", "br", "hr", "span", "div", "section", "article", "aside",
  "em", "i", "strong", "b", "u", "s", "small", "sub", "sup", "mark",
  "ul", "ol", "li",
  "a", "img", "figure", "figcaption",
  "blockquote", "code", "pre", "kbd",
  "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption",
];

const ALLOWED_ATTR = [
  "href", "target", "rel", "title", "alt", "src", "srcset", "sizes",
  "class", "style", "id",
  "colspan", "rowspan", "scope",
  "width", "height",
];

export default function HtmlBody({ html, className = "" }) {
  if (!html) return null;
  const clean = DOMPurify.sanitize(html, {
    ALLOWED_TAGS,
    ALLOWED_ATTR,
    // Никакви javascript:/data: схеми за href/src
    ALLOW_DATA_ATTR: false,
    FORBID_TAGS: ["script", "style", "iframe", "object", "embed", "form", "input", "button", "link", "meta"],
    FORBID_ATTR: ["onerror", "onload", "onclick", "onmouseover", "onfocus", "onblur"],
  });
  return (
    <div
      className={`md-body prose prose-neutral max-w-none ${className}`}
      data-testid="html-body"
      // eslint-disable-next-line react/no-danger
      dangerouslySetInnerHTML={{ __html: clean }}
    />
  );
}
