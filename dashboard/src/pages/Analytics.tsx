import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api/client";
import type { AnalyticsOverview } from "../api/types";

// single validated hue (dataviz six-checks pass on light surface)
const MARK = "#0e8f66";
const GRID = "#e5e8ec";
const INK_MUTED = "#5c6672";

const AXIS = { fontSize: 11, fill: INK_MUTED } as const;
const TOOLTIP_STYLE = {
  borderRadius: 8,
  border: "1px solid #dde1e6",
  fontSize: 12.5,
  boxShadow: "0 2px 8px rgb(16 24 40 / 0.10)",
} as const;

const STAGE_LABELS: Record<string, string> = {
  new: "New",
  contacted: "Contacted",
  qualified: "Qualified",
  booking_sent: "Booking sent",
  won: "Won",
  lost: "Lost",
};

function fmtDuration(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 90) return `${Math.round(seconds)}s`;
  return `${Math.round(seconds / 60)}m`;
}

function pct(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

/** shift UTC hour histogram to Asia/Karachi (UTC+5) */
function toPkt(hours: { hour: number; count: number }[]) {
  const counts = new Array(24).fill(0);
  for (const { hour, count } of hours) counts[(hour + 5) % 24] = count;
  return counts.map((count, hour) => ({
    hour: `${String(hour).padStart(2, "0")}:00`,
    count,
  }));
}

export default function Analytics() {
  const { data } = useQuery({
    queryKey: ["analytics"],
    queryFn: () => api.get<AnalyticsOverview>("/analytics/overview"),
    refetchInterval: 60_000,
  });

  if (!data) return <div className="empty">Loading analytics…</div>;

  const stages = Object.entries(data.leads_by_stage).map(([stage, count]) => ({
    stage: STAGE_LABELS[stage] ?? stage,
    count,
  }));
  const totalTokens14d = data.token_spend_per_day.reduce((sum, d) => sum + d.tokens, 0);

  return (
    <>
      <h1 className="page-title">
        Analytics <span className="sub">last 14–30 days · times in PKT</span>
      </h1>

      <div className="stats">
        <div className="card stat">
          <div className="label">FAQ cache hit rate</div>
          <div className="value">{pct(data.cache_hit_rate)}</div>
          <div className="hint">bot replies answered from KB, 30d</div>
        </div>
        <div className="card stat">
          <div className="label">Lead conversion</div>
          <div className="value">{pct(data.lead_conversion_rate)}</div>
          <div className="hint">won / all leads</div>
        </div>
        <div className="card stat">
          <div className="label">Avg first response</div>
          <div className="value">{fmtDuration(data.avg_first_response_seconds)}</div>
          <div className="hint">first reply to a new conversation, 30d</div>
        </div>
        <div className="card stat">
          <div className="label">Token spend</div>
          <div className="value">{totalTokens14d.toLocaleString()}</div>
          <div className="hint">total tokens, 14d</div>
        </div>
      </div>

      <div className="charts">
        <div className="card chart-card">
          <h3>Conversations per day</h3>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={data.conversations_per_day} margin={{ left: -22, right: 8, top: 4 }}>
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="date" tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }}
                tickFormatter={(d: string) => d.slice(5)} />
              <YAxis tick={AXIS} tickLine={false} axisLine={false} allowDecimals={false} />
              <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ stroke: GRID }} />
              <Line type="monotone" dataKey="count" name="Conversations" stroke={MARK}
                strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="card chart-card">
          <h3>Token spend per day</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={data.token_spend_per_day} margin={{ left: -12, right: 8, top: 4 }}>
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="date" tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }}
                tickFormatter={(d: string) => d.slice(5)} />
              <YAxis tick={AXIS} tickLine={false} axisLine={false} />
              <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "rgb(14 143 102 / 0.06)" }} />
              <Bar dataKey="tokens" name="Tokens" fill={MARK} radius={[4, 4, 0, 0]} maxBarSize={26} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card chart-card">
          <h3>Leads by stage</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={stages} margin={{ left: -22, right: 8, top: 4 }}>
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="stage" tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} />
              <YAxis tick={AXIS} tickLine={false} axisLine={false} allowDecimals={false} />
              <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "rgb(14 143 102 / 0.06)" }} />
              <Bar dataKey="count" name="Leads" fill={MARK} radius={[4, 4, 0, 0]} maxBarSize={34} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card chart-card">
          <h3>Busiest hours (inbound messages, PKT)</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={toPkt(data.busiest_hours_utc)} margin={{ left: -22, right: 8, top: 4 }}>
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="hour" tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} interval={2} />
              <YAxis tick={AXIS} tickLine={false} axisLine={false} allowDecimals={false} />
              <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "rgb(14 143 102 / 0.06)" }} />
              <Bar dataKey="count" name="Messages" fill={MARK} radius={[4, 4, 0, 0]} maxBarSize={18} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </>
  );
}
