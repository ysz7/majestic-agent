import { useEffect, useRef, useState, useCallback } from "react";
import { Download, X } from "lucide-react";
import { wsClient } from "@shared/ws/client";
import type { WsEvent } from "@shared/api/types";

interface LogEntry {
  id:      number;
  badge:   string;
  content: string;
  ts:      string;
  tsRaw:   number;
}

type BadgeFilter = "REASON" | "TOOL_CALL" | "OBSERVE" | "DONE" | "ERR" | "HITL";

const ALL_BADGES: BadgeFilter[] = ["REASON", "TOOL_CALL", "OBSERVE", "DONE", "ERR", "HITL"];

const BADGE_COLOR: Record<string, string> = {
  REASON:    "text-text-muted-2",
  TOOL_CALL: "text-text-dim",
  OBSERVE:   "text-text-muted-2",
  DONE:      "text-[#4ade80]",
  ERR:       "text-red-400",
  HITL:      "text-[#fbbf24]",
};

const BADGE_BG_ACTIVE: Record<string, string> = {
  REASON:    "bg-bg-selected border-border-strong text-text-sub",
  TOOL_CALL: "bg-bg-selected border-border-strong text-text-sub",
  OBSERVE:   "bg-bg-selected border-border-strong text-text-sub",
  DONE:      "bg-[rgba(74,222,128,0.12)] border-[#4ade80]/30 text-[#4ade80]",
  ERR:       "bg-[rgba(248,113,113,0.12)] border-red-400/30 text-red-400",
  HITL:      "bg-[rgba(251,191,36,0.12)] border-[#fbbf24]/30 text-[#fbbf24]",
};

let _seq = 0;

function toEntry(e: WsEvent): LogEntry | null {
  const now = Date.now();
  const ts = new Date(now).toLocaleTimeString("en", { hour12: false });
  switch (e.type) {
    case "step":
      return { id: _seq++, badge: e.step, content: e.content.slice(0, 160), ts, tsRaw: now };
    case "done":
      return { id: _seq++, badge: "DONE", content: `${e.tokens} tok · $${e.cost.toFixed(4)}`, ts, tsRaw: now };
    case "error":
      return { id: _seq++, badge: "ERR",  content: e.message, ts, tsRaw: now };
    case "hitl":
      return { id: _seq++, badge: "HITL", content: `${e.tool}(…)`, ts, tsRaw: now };
    default:
      return null;
  }
}

function toCSV(entries: LogEntry[]): string {
  const header = "timestamp,badge,content";
  const rows = entries.map((e) =>
    [e.ts, e.badge, `"${e.content.replace(/"/g, '""')}"`].join(","),
  );
  return [header, ...rows].join("\n");
}

function downloadCSV(entries: LogEntry[]) {
  const blob = new Blob([toCSV(entries)], { type: "text/csv" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href     = url;
  a.download = `majestic-log-${Date.now()}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export function LogPanel() {
  const [logs,    setLogs]    = useState<LogEntry[]>([]);
  const [filters, setFilters] = useState<Set<BadgeFilter>>(new Set());
  const bottomRef = useRef<HTMLDivElement>(null);
  const autoScroll = useRef(true);

  useEffect(() => {
    return wsClient.on((e) => {
      const entry = toEntry(e);
      if (entry) setLogs((prev) => [...prev.slice(-199), entry]);
    });
  }, []);

  useEffect(() => {
    if (autoScroll.current) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const toggleFilter = useCallback((badge: BadgeFilter) => {
    setFilters((prev) => {
      const next = new Set(prev);
      next.has(badge) ? next.delete(badge) : next.add(badge);
      return next;
    });
  }, []);

  const clearFilters = () => setFilters(new Set());

  const visible = filters.size === 0
    ? logs
    : logs.filter((l) => filters.has(l.badge as BadgeFilter));

  return (
    <div className="flex flex-col h-full rounded-node border border-border overflow-hidden bg-bg-elevated">
      {/* Header */}
      <div className="px-[11px] py-[6px] border-b border-border flex-shrink-0 flex items-center gap-[6px]">
        <span className="text-2xs text-text-muted-3 uppercase tracking-[1.2px] font-semibold mr-[3px]">
          Log
        </span>

        {/* Filter chips */}
        <div className="flex items-center gap-[3px] flex-1 flex-wrap">
          {ALL_BADGES.map((b) => {
            const active = filters.has(b);
            return (
              <button
                key={b}
                onClick={() => toggleFilter(b)}
                className={`px-[6px] py-[2px] text-[10px] rounded-[5px] border transition-colors ${
                  active
                    ? (BADGE_BG_ACTIVE[b] ?? "bg-bg-selected border-border-strong text-text-sub")
                    : "border-border text-text-muted-3 hover:text-text-sub hover:border-border-strong"
                }`}
              >
                {b}
              </button>
            );
          })}
          {filters.size > 0 && (
            <button
              onClick={clearFilters}
              className="ml-[1px] text-text-muted-3 hover:text-text-sub"
              title="Clear filters"
            >
              <X size={10} />
            </button>
          )}
        </div>

        {/* Export CSV */}
        <button
          onClick={() => downloadCSV(visible)}
          disabled={visible.length === 0}
          title="Export visible log as CSV"
          className="text-text-muted-3 hover:text-text-sub disabled:opacity-30 flex-shrink-0"
        >
          <Download size={12} />
        </button>
      </div>

      {/* Log rows */}
      <div
        className="flex-1 overflow-y-auto px-[9px] py-[7px] font-mono flex flex-col gap-[4px]"
        onScroll={(e) => {
          const el = e.currentTarget;
          autoScroll.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
        }}
      >
        {visible.length === 0 ? (
          <div className="text-xs text-text-muted-3 mt-1">
            {logs.length === 0 ? "Waiting…" : "No entries match the filter."}
          </div>
        ) : (
          visible.map((l) => (
            <div key={l.id} className="flex items-start gap-[5px] text-xs leading-[1.45]">
              <span className="text-text-muted-3 flex-shrink-0 w-[40px]">{l.ts}</span>
              <span
                className={`flex-shrink-0 w-[54px] uppercase ${BADGE_COLOR[l.badge] ?? "text-text-muted-2"}`}
              >
                {l.badge}
              </span>
              {l.content && (
                <span className="text-text-dim break-all">{l.content}</span>
              )}
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>

      {/* Footer count */}
      {logs.length > 0 && (
        <div className="px-[11px] py-[4px] border-t border-border flex-shrink-0 flex items-center justify-between">
          <span className="text-2xs text-text-muted-3">
            {visible.length}{filters.size > 0 ? ` / ${logs.length}` : ""} entries
          </span>
          {logs.length >= 200 && (
            <span className="text-2xs text-text-muted-3">last 200</span>
          )}
        </div>
      )}
    </div>
  );
}
