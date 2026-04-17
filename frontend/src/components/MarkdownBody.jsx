import React from "react";
import ReactMarkdown from "react-markdown";

/**
 * Thin wrapper around react-markdown with consistent typography for all CMS-driven pages.
 */
export default function MarkdownBody({ children }) {
  if (!children) return null;
  return (
    <div className="md-body prose prose-neutral max-w-none">
      <ReactMarkdown
        components={{
          h1: ({ node, ...p }) => <h1 className="font-serif text-3xl lg:text-4xl mt-8 mb-3" {...p} />,
          h2: ({ node, ...p }) => <h2 className="font-serif text-2xl lg:text-3xl mt-8 mb-3" {...p} />,
          h3: ({ node, ...p }) => <h3 className="font-serif text-xl mt-6 mb-2" {...p} />,
          p:  ({ node, ...p }) => <p className="text-base leading-relaxed text-[hsl(var(--ink))] mt-3" {...p} />,
          ul: ({ node, ...p }) => <ul className="list-disc pl-6 mt-3 space-y-1.5 text-base leading-relaxed" {...p} />,
          ol: ({ node, ...p }) => <ol className="list-decimal pl-6 mt-3 space-y-1.5 text-base leading-relaxed" {...p} />,
          li: ({ node, ...p }) => <li className="leading-relaxed" {...p} />,
          a:  ({ node, ...p }) => <a className="text-[hsl(var(--accent))] hover:underline" target="_blank" rel="noreferrer" {...p} />,
          strong: ({ node, ...p }) => <strong className="font-semibold text-[hsl(var(--ink))]" {...p} />,
          blockquote: ({ node, ...p }) => <blockquote className="border-l-4 border-[hsl(var(--accent))] pl-4 italic text-[hsl(var(--ink-muted))] mt-4" {...p} />,
          hr: () => <hr className="my-8 border-[hsl(var(--line))]" />,
          code: ({ node, ...p }) => <code className="bg-[hsl(var(--surface))] px-1.5 py-0.5 text-[13px] font-mono rounded" {...p} />,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
