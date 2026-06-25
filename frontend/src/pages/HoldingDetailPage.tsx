import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, changeClass, formatMoney, formatOrder, Holding } from "../api";

export default function HoldingDetailPage() {
  const { ticker = "" } = useParams();
  const [holding, setHolding] = useState<Holding | null>(null);
  const [shares, setShares] = useState("");
  const [cost, setCost] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    if (!ticker) return;
    setLoading(true);
    setError("");
    try {
      const data = await api.getHolding(ticker);
      setHolding(data);
      setShares(data.shares != null ? String(data.shares) : "");
      setCost(data.cost_basis != null ? String(data.cost_basis) : "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [ticker]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleSave(e: FormEvent) {
    e.preventDefault();
    if (!ticker) return;
    setSaving(true);
    setError("");
    setSaved(false);
    try {
      const body: Record<string, number> = {};
      if (shares.trim()) body.shares = Number(shares);
      if (cost.trim()) body.cost_basis = Number(cost);
      const updated = await api.updateHolding(ticker, body);
      setHolding(updated);
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <p className="muted">加载中…</p>;
  if (!holding) return <p className="error">{error || "未找到持仓"}</p>;

  const currency = holding.currency || "USD";

  return (
    <div>
      <Link to="/" className="muted back-link">
        ← 返回持仓
      </Link>
      <h1>{holding.name}</h1>
      <p className="muted">{holding.ticker}</p>

      <div className="card">
        <div className="price-lg">
          {holding.price != null ? formatMoney(holding.price, currency) : "—"}
        </div>
        <div className={changeClass(holding.change_pct)}>
          {holding.change_pct != null ? `${holding.change_pct >= 0 ? "+" : ""}${holding.change_pct.toFixed(2)}%` : ""}
        </div>
        <div className="meta row">
          <span className={`pill pill-${holding.portfolio_action}`}>{holding.portfolio_action}</span>
          {holding.pnl_pct != null && (
            <span className={changeClass(holding.pnl_pct)}>
              浮盈 {holding.pnl_pct >= 0 ? "+" : ""}
              {holding.pnl_pct.toFixed(1)}%
            </span>
          )}
        </div>
      </div>

      {holding.order && (
        <div className="card">
          <div className="section-title">今日挂单</div>
          <div className="title">{holding.order.side}</div>
          <div>{formatOrder(holding)}</div>
          <p className="muted pre-wrap">{holding.order.note}</p>
        </div>
      )}

      <form className="card" onSubmit={handleSave}>
        <div className="section-title">修改持仓</div>
        <label className="field">
          <span>股数</span>
          <input inputMode="decimal" value={shares} onChange={(e) => setShares(e.target.value)} />
        </label>
        <label className="field">
          <span>成本价</span>
          <input inputMode="decimal" value={cost} onChange={(e) => setCost(e.target.value)} />
        </label>
        <button className="btn" type="submit" disabled={saving}>
          {saving ? "保存中…" : "保存"}
        </button>
        {saved && <p className="up">已保存到 holdings_live.json</p>}
        {error && <p className="error">{error}</p>}
      </form>
    </div>
  );
}
