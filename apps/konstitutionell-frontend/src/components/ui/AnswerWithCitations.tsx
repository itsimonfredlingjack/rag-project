import React, { useDeferredValue, useMemo } from "react";
import clsx from "clsx";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";

import type { Source } from "../../stores/useAppStore";
import { useAppStore } from "../../stores/useAppStore";
import { CITATION_RE } from "./citations";

type AnswerWithCitationsProps = {
  answer: string;
  sources: Source[];
  className?: string;
};

/* ------------------------------------------------------------------ */
/*  Citation placeholder logic                                         */
/* ------------------------------------------------------------------ */

const CITE_PLACEHOLDER = /%%CITE:(\d+)%%/g;

/** Replace [1], [Källa 1] etc. with %%CITE:N%% so the markdown parser
 *  doesn't swallow them as link references. */
function prepareCitations(raw: string): string {
  return raw.replace(CITATION_RE, (_, n) => `%%CITE:${n}%%`);
}

/* ------------------------------------------------------------------ */
/*  Recursive child-walker that swaps placeholders for buttons         */
/* ------------------------------------------------------------------ */

function injectCitations(
  children: React.ReactNode,
  sources: Source[],
  activeSourceId: string | null,
  setHoveredSource: (id: string | null) => void,
  toggleLockedSource: (id: string) => void,
  setCitationTarget: (rect: DOMRect | null) => void,
): React.ReactNode {
  return React.Children.map(children, (child) => {
    if (typeof child === "string") {
      if (!CITE_PLACEHOLDER.test(child)) return child;

      // Split string around %%CITE:N%% tokens
      const parts: React.ReactNode[] = [];
      let lastIdx = 0;
      for (const m of child.matchAll(CITE_PLACEHOLDER)) {
        const idx = m.index ?? 0;
        if (idx > lastIdx) parts.push(child.slice(lastIdx, idx));

        const n = Number(m[1]);
        const src = Number.isFinite(n) ? sources[n - 1] : undefined;
        const sourceId = src?.id ?? null;
        const isKnown = Boolean(sourceId);
        const isActive = sourceId && activeSourceId === sourceId;

        parts.push(
          <button
            key={`cite-${idx}-${n}`}
            type="button"
            disabled={!isKnown}
            onMouseEnter={(e) => {
              if (!sourceId) return;
              setHoveredSource(sourceId);
              setCitationTarget(e.currentTarget.getBoundingClientRect());
            }}
            onMouseLeave={() => {
              setCitationTarget(null);
              setHoveredSource(null);
            }}
            onClick={(e) => {
              if (!sourceId) return;
              toggleLockedSource(sourceId);
              setCitationTarget(e.currentTarget.getBoundingClientRect());
            }}
            className={clsx(
              "inline-flex items-center align-baseline mx-1",
              "px-2 py-0.5 rounded-full border",
              "text-[11px] font-mono tracking-wider",
              isKnown
                ? "bg-stone-100/70 border-stone-300/70 text-stone-700 hover:bg-stone-100"
                : "bg-stone-100/40 border-stone-200/70 text-stone-400 cursor-not-allowed",
              isActive && "ring-2 ring-teal-700/20",
            )}
            aria-label={isKnown ? `Citation ${n}` : "Unknown citation"}
          >
            [{n}]
          </button>,
        );

        lastIdx = idx + m[0].length;
      }
      if (lastIdx < child.length) parts.push(child.slice(lastIdx));
      return <>{parts}</>;
    }

    // Recurse into React elements that have children
    if (
      React.isValidElement(child) &&
      child.props &&
      typeof child.props === "object" &&
      "children" in child.props
    ) {
      return React.cloneElement(
        child as React.ReactElement<{ children?: React.ReactNode }>,
        {},
        injectCitations(
          (child.props as { children?: React.ReactNode }).children,
          sources,
          activeSourceId,
          setHoveredSource,
          toggleLockedSource,
          setCitationTarget,
        ),
      );
    }

    return child;
  });
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function AnswerWithCitations({
  answer,
  sources,
  className,
}: AnswerWithCitationsProps) {
  const activeSourceId = useAppStore((s) => s.activeSourceId);
  const setHoveredSource = useAppStore((s) => s.setHoveredSource);
  const toggleLockedSource = useAppStore((s) => s.toggleLockedSource);
  const setCitationTarget = useAppStore((s) => s.setCitationTarget);

  // Defer markdown re-parsing during rapid streaming updates
  const deferredAnswer = useDeferredValue(answer);

  const preparedAnswer = useMemo(
    () => prepareCitations(deferredAnswer),
    [deferredAnswer],
  );

  /** Wrap children of any markdown element to inject citation buttons */
  const cite = (children: React.ReactNode) =>
    injectCitations(
      children,
      sources,
      activeSourceId,
      setHoveredSource,
      toggleLockedSource,
      setCitationTarget,
    );

  const components: Components = {
    p: ({ children }) => <p className="mb-3 last:mb-0">{cite(children)}</p>,
    strong: ({ children }) => (
      <strong className="font-semibold">{cite(children)}</strong>
    ),
    em: ({ children }) => <em>{cite(children)}</em>,
    ul: ({ children }) => (
      <ul className="list-disc pl-5 mb-3 space-y-1">{children}</ul>
    ),
    ol: ({ children }) => (
      <ol className="list-decimal pl-5 mb-3 space-y-1">{children}</ol>
    ),
    li: ({ children }) => <li className="pl-1">{cite(children)}</li>,
    h1: ({ children }) => (
      <h1 className="font-bold text-lg mt-5 mb-2">{cite(children)}</h1>
    ),
    h2: ({ children }) => (
      <h2 className="font-bold text-base mt-4 mb-2">{cite(children)}</h2>
    ),
    h3: ({ children }) => (
      <h3 className="font-semibold text-base mt-4 mb-2">{cite(children)}</h3>
    ),
    h4: ({ children }) => (
      <h4 className="font-semibold text-sm mt-3 mb-1">{cite(children)}</h4>
    ),
    blockquote: ({ children }) => (
      <blockquote className="border-l-3 border-teal-700/30 pl-4 my-3 text-stone-600 italic">
        {children}
      </blockquote>
    ),
    code: ({ children, className: codeClassName }) => {
      const isBlock =
        typeof codeClassName === "string" &&
        codeClassName.startsWith("language-");
      if (isBlock) {
        return (
          <code
            className={clsx(
              "block bg-stone-100 rounded-lg p-3 my-3 text-[13px] font-mono overflow-x-auto whitespace-pre",
              codeClassName,
            )}
          >
            {children}
          </code>
        );
      }
      return (
        <code className="bg-stone-100 rounded px-1.5 py-0.5 text-[13px] font-mono">
          {children}
        </code>
      );
    },
    pre: ({ children }) => <pre className="my-3">{children}</pre>,
    table: ({ children }) => (
      <div className="overflow-x-auto my-3">
        <table className="min-w-full text-sm border-collapse">{children}</table>
      </div>
    ),
    thead: ({ children }) => (
      <thead className="border-b border-stone-300">{children}</thead>
    ),
    th: ({ children }) => (
      <th className="text-left px-3 py-1.5 font-semibold text-stone-700">
        {children}
      </th>
    ),
    td: ({ children }) => (
      <td className="px-3 py-1.5 border-t border-stone-200">
        {cite(children)}
      </td>
    ),
    hr: () => <hr className="my-4 border-stone-200" />,
    a: ({ href, children }) => (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-teal-700 underline underline-offset-2 hover:text-teal-800"
      >
        {cite(children)}
      </a>
    ),
  };

  return (
    <div className={clsx("break-words", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {preparedAnswer}
      </ReactMarkdown>
    </div>
  );
}
