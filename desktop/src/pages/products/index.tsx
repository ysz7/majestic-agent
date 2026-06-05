import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Sparkles, Loader2, ChevronDown, ChevronRight,
  DollarSign, Wrench, Megaphone, Target, ShieldCheck, FlaskConical,
} from "lucide-react";
import { productsApi } from "@shared/api/client";
import { useAgentStore } from "@store/agentStore";
import type { ProductItem } from "@shared/api/types";
import { cn } from "@shared/lib/cn";

function scoreColor(score: number): string {
  if (score >= 80) return "#4ade80";
  if (score >= 60) return "#fbbf24";
  return "#f87171";
}

function ProductCard({ item, rank }: { item: ProductItem; rank: number }) {
  const [open, setOpen] = useState(rank === 1);
  const ma = item.monetization_audit ?? {};

  return (
    <div className="rounded-[12px] border border-border bg-node-gradient overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-[10px] px-[13px] py-[11px] text-left hover:bg-bg-active/40 transition-colors"
      >
        <span className="text-md text-text-muted-3 font-semibold w-[18px] flex-shrink-0">
          #{rank}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-[7px]">
            <span className="text-md text-text-sub truncate">{item.name}</span>
            <span className="text-[9px] text-text-muted-2 border border-border rounded-[5px] px-[5px] py-[1px] flex-shrink-0">
              {item.type}
            </span>
          </div>
          <div className="text-xs text-text-muted-2 truncate mt-[2px]">{item.one_liner}</div>
        </div>
        {/* Score badge */}
        <div
          className="flex flex-col items-center justify-center rounded-[8px] px-[8px] py-[4px] flex-shrink-0"
          style={{ background: "rgba(255,255,255,0.04)", border: `1px solid ${scoreColor(item.sellability_score)}40` }}
        >
          <span className="text-md font-semibold" style={{ color: scoreColor(item.sellability_score) }}>
            {item.sellability_score}
          </span>
          <span className="text-[8px] text-text-muted-3 uppercase tracking-[0.5px]">score</span>
        </div>
        {open ? <ChevronDown size={13} className="text-text-faint flex-shrink-0" />
              : <ChevronRight size={13} className="text-text-faint flex-shrink-0" />}
      </button>

      {/* Body */}
      {open && (
        <div className="px-[13px] pb-[13px] flex flex-col gap-[9px] text-xs text-text-dim border-t border-border pt-[11px]">
          <Field label="For" value={item.audience} />
          <Field label="Demand" value={item.demand} />
          <Field label="Why now" value={item.why_now} />

          {/* Monetization audit */}
          <Section icon={DollarSign} title="Monetization audit">
            <KV k="Pricing"  v={`${ma.pricing_model ?? ""}${ma.price_points ? ` — ${ma.price_points}` : ""}`} />
            <KV k="Revenue"  v={ma.revenue_range} />
            <KV k="Margin"   v={ma.margin} />
            <KV k="Time to $1" v={ma.time_to_first_dollar} />
            <KV k="Build"    v={ma.build_effort} />
          </Section>

          <Section icon={Wrench} title="Build stack (secret tools)">
            <Chips items={item.build_stack} />
          </Section>
          <Section icon={Megaphone} title="Distribution (secret channels)">
            <Chips items={item.distribution} />
          </Section>

          <Section icon={Target} title="Competition gap">
            <p className="text-text-muted-2 leading-[1.5]">{item.competition_gap}</p>
          </Section>
          <Section icon={ShieldCheck} title="Unfair advantage">
            <p className="text-text-muted-2 leading-[1.5]">{item.unfair_advantage}</p>
          </Section>
          <Section icon={FlaskConical} title="Validation">
            <p className="text-text-muted-2 leading-[1.5]">{item.validation_test}</p>
          </Section>

          {item.first_3_steps?.length ? (
            <Section icon={Sparkles} title="First 3 steps">
              <ol className="list-decimal pl-[16px] flex flex-col gap-[3px] text-text-muted-2">
                {item.first_3_steps.map((s, i) => <li key={i}>{s}</li>)}
              </ol>
            </Section>
          ) : null}
        </div>
      )}
    </div>
  );
}

function Field({ label, value }: { label: string; value?: string }) {
  if (!value) return null;
  return (
    <div>
      <span className="text-[9px] text-text-muted-3 uppercase tracking-[1px] font-semibold">{label}</span>
      <p className="text-text-dim leading-[1.5] mt-[2px]">{value}</p>
    </div>
  );
}

function Section({ icon: Icon, title, children }: { icon: React.ElementType; title: string; children: React.ReactNode }) {
  return (
    <div className="border-t border-border pt-[8px]">
      <div className="flex items-center gap-[5px] mb-[5px]">
        <Icon size={11} className="text-text-muted-2" />
        <span className="text-[9px] text-text-muted-3 uppercase tracking-[1px] font-semibold">{title}</span>
      </div>
      {children}
    </div>
  );
}

function KV({ k, v }: { k: string; v?: string }) {
  if (!v) return null;
  return (
    <div className="flex gap-[6px] leading-[1.5]">
      <span className="text-text-muted-3 flex-shrink-0 w-[68px]">{k}</span>
      <span className="text-text-dim">{v}</span>
    </div>
  );
}

function Chips({ items }: { items?: string[] }) {
  if (!items?.length) return <span className="text-text-muted-3">—</span>;
  return (
    <div className="flex flex-wrap gap-[4px]">
      {items.map((s, i) => (
        <span key={i} className="text-[9px] text-text-muted-2 border border-border rounded-[5px] px-[6px] py-[2px]">
          {s}
        </span>
      ))}
    </div>
  );
}

export function ProductsPage() {
  const activeProfile = useAgentStore((s) => s.activeProfile);
  const qc = useQueryClient();
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  const reports = useQuery({
    queryKey: ["products", activeProfile],
    queryFn:  () => productsApi.list(activeProfile!),
    enabled:  !!activeProfile,
  });

  // Default to the latest report.
  useEffect(() => {
    const list = reports.data?.reports ?? [];
    if (!selectedDate && list.length) setSelectedDate(list[0].date);
  }, [reports.data, selectedDate]);

  const report = useQuery({
    queryKey: ["product-report", activeProfile, selectedDate],
    queryFn:  () => productsApi.get(activeProfile!, selectedDate!),
    enabled:  !!activeProfile && !!selectedDate,
  });

  const run = useMutation({
    mutationFn: () => productsApi.run(activeProfile!, 30),
    onSuccess:  (data) => {
      qc.invalidateQueries({ queryKey: ["products", activeProfile] });
      setSelectedDate(data.date);
      qc.setQueryData(["product-report", activeProfile, data.date], data);
    },
  });

  const items = report.data?.items ?? [];
  const reportList = reports.data?.reports ?? [];

  return (
    <div className="w-full h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-[14px] py-[11px] flex-shrink-0">
        <div className="flex items-center gap-[8px]">
          <Sparkles size={14} className="text-text-sub" />
          <span className="text-md text-text-sub">Solo Product Forge</span>
          {reportList.length > 0 && (
            <select
              value={selectedDate ?? ""}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="ml-[6px] bg-bg-elevated border border-border rounded-[7px] px-[8px] py-[4px] text-xs text-text-dim outline-none focus:border-border-strong"
            >
              {reportList.map((r) => (
                <option key={r.date} value={r.date}>{r.date} ({r.count})</option>
              ))}
            </select>
          )}
        </div>
        <button
          onClick={() => run.mutate()}
          disabled={run.isPending || !activeProfile}
          className={cn(
            "flex items-center gap-[6px] px-[11px] py-[6px] rounded-[8px] border text-xs transition-colors",
            "border-border text-text-dim hover:text-text-sub hover:border-border-strong disabled:opacity-40",
          )}
        >
          {run.isPending ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
          {run.isPending ? "Forging…" : "Generate"}
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto px-[14px] pb-[14px]">
        {run.isError && (
          <div className="text-xs text-red-300 mb-[10px]">
            {(run.error as Error)?.message ?? "Generation failed"}
          </div>
        )}

        {run.isPending ? (
          <div className="h-full flex flex-col items-center justify-center gap-[10px] text-text-muted-2">
            <Loader2 size={22} className="animate-spin" />
            <span className="text-xs">Analyzing intelligence & forging products…</span>
          </div>
        ) : !activeProfile ? (
          <Empty text="No active profile." />
        ) : report.isLoading && selectedDate ? (
          <div className="text-xs text-text-muted-2">Loading…</div>
        ) : items.length === 0 ? (
          <Empty text="No product reports yet. Click Generate to forge your first TOP-10." />
        ) : (
          <div className="flex flex-col gap-[8px] max-w-[760px]">
            {items.map((it, i) => (
              <ProductCard key={i} item={it} rank={i + 1} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return (
    <div className="h-full flex items-center justify-center">
      <span className="text-xs text-text-muted-2 text-center max-w-[280px] leading-[1.6]">{text}</span>
    </div>
  );
}
