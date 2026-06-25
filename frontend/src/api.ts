export type OrderLeg = { price: number; shares: number };

export type HoldingOrder = {
  side: string;
  legs: OrderLeg[];
  note: string;
};

export type Holding = {
  ticker: string;
  name: string;
  market: string;
  shares?: number | null;
  cost_basis?: number | null;
  price?: number | null;
  change_pct?: number | null;
  currency?: string | null;
  market_value?: number | null;
  pnl_pct?: number | null;
  pnl_amount?: number | null;
  weight_pct?: number | null;
  portfolio_action: string;
  action_reasons: string[];
  order?: HoldingOrder | null;
  error?: string | null;
};

export type BriefSection = {
  title: string;
  lines: string[];
};

export type Brief = {
  generated_at: string;
  title: string;
  conclusion: string;
  sections: BriefSection[];
  markdown: string;
};

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) || "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || res.statusText);
  }
  const data = (await res.json()) as T;
  if (path.includes("/holdings") && !Array.isArray(data)) {
    throw new Error("API 返回格式异常，请检查 VITE_API_BASE 或重启 dev.sh");
  }
  return data;
}

export const api = {
  listHoldings: () => request<Holding[]>("/api/holdings"),
  getHolding: (ticker: string) => request<Holding>(`/api/holdings/${encodeURIComponent(ticker)}`),
  updateHolding: (ticker: string, body: Record<string, number | string>) =>
    request<Holding>(`/api/holdings/${encodeURIComponent(ticker)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  todayBrief: () => request<Brief>("/api/brief/today"),
};

export function formatMoney(value: number, currency: string) {
  const symbol = { USD: "$", AUD: "A$", CNY: "¥" }[currency] || `${currency} `;
  return `${symbol}${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

export function changeClass(value?: number | null) {
  if (value == null) return "";
  return value >= 0 ? "up" : "down";
}

export function formatOrder(holding: Holding) {
  const order = holding.order;
  if (!order || order.side === "观望" || !order.legs?.length) return "—";
  const c = holding.currency || "USD";
  return order.legs
    .map((leg) => `${formatMoney(leg.price, c)} × ${leg.shares}股`)
    .join(" + ");
}
