"use client";

import { useState } from "react";

/**
 * Shared lightweight markdown renderer — no external dependency.
 * Handles: fenced code blocks, tables, bullet/numbered lists, headings,
 * bold, italic, inline code, and markdown links [label](url).
 */

export function FormattedContent({
  content,
  onEditableBlock,
}: {
  content: string;
  onEditableBlock?: (text: string) => void;
}) {
  if (!content) return null;

  const parts = content.split(/(```[\s\S]*?```)/g);

  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith("```")) {
          const code = part.replace(/^```\w*\n?/, "").replace(/```$/, "");
          if (onEditableBlock) {
            return <EditableBlock key={i} code={code} onUse={onEditableBlock} />;
          }
          return (
            <pre key={i} className="bg-gray-900 text-gray-100 rounded-lg px-4 py-3 text-xs overflow-x-auto my-2">
              <code>{code}</code>
            </pre>
          );
        }
        return <BlockMarkdown key={i} text={part} />;
      })}
    </>
  );
}

function EditableBlock({ code, onUse }: { code: string; onUse: (text: string) => void }) {
  const [value, setValue] = useState(code);
  return (
    <div className="my-3 rounded-lg border-2 border-dashed border-indigo-300 bg-indigo-50 overflow-hidden">
      <div className="flex items-center justify-between px-3 py-1.5 bg-indigo-100 border-b border-indigo-200">
        <span className="text-[10px] font-semibold text-indigo-600 uppercase tracking-widest flex items-center gap-1">
          ✏️ Edit before sending
        </span>
      </div>
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        rows={value.split("\n").length + 1}
        className="w-full px-3 py-2.5 text-xs font-mono text-gray-800 bg-white resize-none focus:outline-none focus:ring-1 focus:ring-indigo-400 leading-relaxed"
        spellCheck={false}
      />
      <div className="flex justify-end px-3 py-2 bg-indigo-50 border-t border-indigo-200">
        <button
          onClick={() => onUse(value)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-md transition-colors"
        >
          Use this ↗
        </button>
      </div>
    </div>
  );
}

function BlockMarkdown({ text }: { text: string }) {
  const lines = text.split("\n");
  const nodes: React.ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // ── Markdown table ──────────────────────────────────────────────────────
    if (
      line.trimStart().startsWith("|") &&
      i + 1 < lines.length &&
      /^\s*\|[\s\-|:]+\|\s*$/.test(lines[i + 1])
    ) {
      const tableLines: string[] = [];
      while (i < lines.length && lines[i].trimStart().startsWith("|")) {
        tableLines.push(lines[i]);
        i++;
      }
      nodes.push(<MarkdownTable key={`tbl-${i}`} rows={tableLines} />);
      continue;
    }

    // ── Bullet list ─────────────────────────────────────────────────────────
    if (/^(\s*)([-*•])\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^(\s*)([-*•])\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^(\s*)([-*•])\s+/, ""));
        i++;
      }
      nodes.push(
        <ul key={`ul-${i}`} className="list-disc list-outside ml-4 my-1 space-y-0.5">
          {items.map((item, j) => (
            <li key={j} className="text-sm leading-relaxed">
              <InlineMarkdown text={item} />
            </li>
          ))}
        </ul>
      );
      continue;
    }

    // ── Numbered list ───────────────────────────────────────────────────────
    if (/^\s*\d+\.\s+/.test(line)) {
      const startMatch = line.match(/^\s*(\d+)\.\s+/);
      const startNum = startMatch ? parseInt(startMatch[1], 10) : 1;
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+\.\s+/, ""));
        i++;
      }
      nodes.push(
        <ol key={`ol-${i}`} start={startNum} className="list-decimal list-outside ml-4 my-1 space-y-0.5">
          {items.map((item, j) => (
            <li key={j} className="text-sm leading-relaxed">
              <InlineMarkdown text={item} />
            </li>
          ))}
        </ol>
      );
      continue;
    }

    // ── Headings ────────────────────────────────────────────────────────────
    if (/^##\s+/.test(line)) {
      nodes.push(
        <h4 key={`h4-${i}`} className="font-semibold text-gray-800 mt-3 mb-1 text-sm">
          <InlineMarkdown text={line.replace(/^##\s+/, "")} />
        </h4>
      );
      i++;
      continue;
    }
    if (/^#\s+/.test(line)) {
      nodes.push(
        <h3 key={`h3-${i}`} className="font-bold text-gray-900 mt-3 mb-1 text-sm">
          <InlineMarkdown text={line.replace(/^#\s+/, "")} />
        </h3>
      );
      i++;
      continue;
    }

    // ── Horizontal rule ─────────────────────────────────────────────────────
    if (/^[-*_]{3,}\s*$/.test(line)) {
      nodes.push(<hr key={`hr-${i}`} className="my-2 border-gray-200" />);
      i++;
      continue;
    }

    // ── Blank line / paragraph ──────────────────────────────────────────────
    if (line.trim() === "") {
      nodes.push(<div key={`br-${i}`} className="h-1.5" />);
    } else {
      nodes.push(
        <p key={`p-${i}`} className="text-sm leading-relaxed">
          <InlineMarkdown text={line} />
        </p>
      );
    }
    i++;
  }

  return <>{nodes}</>;
}

function MarkdownTable({ rows }: { rows: string[] }) {
  const parseCells = (row: string) =>
    row
      .trim()
      .replace(/^\||\|$/g, "")
      .split("|")
      .map((c) => c.trim());

  const isSeparator = (row: string) => /^\s*\|[\s\-|:]+\|\s*$/.test(row);

  const headers = parseCells(rows[0]);
  const bodyRows = rows.filter((_, idx) => idx > 0 && !isSeparator(rows[idx]));

  return (
    <div className="overflow-x-auto my-3 rounded-lg border border-gray-200 shadow-sm">
      <table className="min-w-full text-xs divide-y divide-gray-200">
        <thead className="bg-indigo-50">
          <tr>
            {headers.map((h, i) => (
              <th key={i} className="px-3 py-2 text-left font-semibold text-indigo-800 whitespace-nowrap">
                <InlineMarkdown text={h} />
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-100">
          {bodyRows.map((row, ri) => (
            <tr key={ri} className={ri % 2 === 0 ? "bg-white" : "bg-gray-50"}>
              {parseCells(row).map((cell, ci) => (
                <td key={ci} className="px-3 py-2 text-gray-700 align-top">
                  <InlineMarkdown text={cell} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function InlineMarkdown({ text }: { text: string }) {
  return <>{renderInline(text)}</>;
}

function renderInline(text: string): React.ReactNode {
  const segments: React.ReactNode[] = [];
  const regex = /(\[([^\]]+)\]\((https?:\/\/[^)]+)\)|\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
  let last = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > last) segments.push(text.slice(last, match.index));
    const token = match[0];
    if (token.startsWith("[")) {
      segments.push(
        <a key={match.index} href={match[3]} target="_blank" rel="noopener noreferrer"
           className="underline text-indigo-600 hover:text-indigo-800">
          {match[2]}
        </a>
      );
    } else if (token.startsWith("**")) {
      segments.push(<strong key={match.index}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("*")) {
      segments.push(<em key={match.index}>{token.slice(1, -1)}</em>);
    } else {
      segments.push(
        <code key={match.index} className="bg-gray-100 text-gray-800 px-1 py-0.5 rounded text-xs font-mono">
          {token.slice(1, -1)}
        </code>
      );
    }
    last = match.index + token.length;
  }
  if (last < text.length) segments.push(text.slice(last));
  return segments;
}
