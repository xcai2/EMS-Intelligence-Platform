"use client";

import { Download } from "lucide-react";

export interface TablePayload {
  title: string;
  columns: string[];
  rows: string[][];
}

interface TableAnswerProps {
  narrativeText?: string;
  tablePayload: TablePayload;
}

function exportCSV(tablePayload: TablePayload) {
  const { title, columns, rows } = tablePayload;
  const escape = (v: string) =>
    v.includes(",") || v.includes('"') || v.includes("\n")
      ? `"${v.replace(/"/g, '""')}"`
      : v;

  const lines = [
    columns.map(escape).join(","),
    ...rows.map((row) => row.map(escape).join(",")),
  ];

  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${title || "table"}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export function TableAnswer({ narrativeText, tablePayload }: TableAnswerProps) {
  const { title, columns, rows } = tablePayload;

  return (
    <div className="relative space-y-2">
      {/* Export button — top-right of bubble */}
      <button
        onClick={() => exportCSV(tablePayload)}
        title="Export CSV"
        className="absolute -top-1 right-0 flex items-center gap-1 rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-[10px] font-medium text-slate-500 hover:border-slate-400 hover:bg-white hover:text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400 dark:hover:border-slate-500 dark:hover:bg-slate-700 dark:hover:text-slate-200 transition-colors"
      >
        <Download className="h-2.5 w-2.5 shrink-0" />
        Export
      </button>

      {narrativeText && (
        <p className="text-sm text-slate-600 dark:text-slate-300 pr-16">{narrativeText}</p>
      )}

      {title && (
        <p className="text-sm font-semibold text-slate-800 dark:text-slate-100 pr-16">{title}</p>
      )}

      <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-700">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50 dark:bg-slate-800">
            <tr>
              {columns.map((col, i) => (
                <th
                  key={i}
                  className={`px-4 py-2.5 font-semibold text-slate-700 dark:text-slate-200 border-b border-slate-200 dark:border-slate-700 whitespace-nowrap ${
                    i === 0 ? "text-left" : "text-right"
                  }`}
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {rows.length === 0 ? (
              <tr>
                <td
                  colSpan={columns.length}
                  className="px-4 py-3 text-center text-slate-400 dark:text-slate-500 italic"
                >
                  No verified data available
                </td>
              </tr>
            ) : (
              rows.map((row, ri) => (
                <tr
                  key={ri}
                  className="bg-white dark:bg-slate-900 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors"
                >
                  {row.map((cell, ci) => (
                    <td
                      key={ci}
                      className={`px-4 py-2.5 text-slate-800 dark:text-slate-100 whitespace-nowrap ${
                        ci === 0 ? "text-left font-medium" : "text-right tabular-nums"
                      }`}
                    >
                      {cell === "N/A" ? (
                        <span className="text-slate-400 dark:text-slate-500">N/A</span>
                      ) : (
                        cell
                      )}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
