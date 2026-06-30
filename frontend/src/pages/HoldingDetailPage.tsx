import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, changeClass, formatActionDetail, formatMoney, formatOrder, Holding } from "../api";

export default function HoldingDetailPage() {
  const { ticker = "" } = useParams();
  const navigate = useNavigate();
  const [holding, setHolding] = useState<Holding | null>(null);
  const [name, setName] = useState("");
  const [shares, setShares] = useState("");
  const [cost, setCost] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    if (!ticker) return;
    setLoading(true);
    setError("");
    try {
      const data = await api.getHolding(ticker);
      setHolding(data);
      setName(data.name || "");
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
      const body: Record<string, number | string> = {};
      if (name.trim()) body.name = name.trim();
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

  async function handleDelete() {
    if (!ticker || !window.confirm(`确定删除 ${ticker}？`)) return;
    setDeleting(true);
    setError("");
    try {
      await api.deleteHolding(ticker);
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    } finally {
      setDeleting(false);
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

      {(holding.stop_loss != null || holding.target_price != null) && (
        <div className="card">
          <div className="section-title">今日动态价位</div>
          <div className="row">
            <span className="muted">止损参考</span>
            <span className="down">
              {holding.stop_loss != null ? formatMoney(holding.stop_loss, currency) : "—"}
            </span>
          </div>
          <div className="row">
            <span className="muted">目标价</span>
            <span className="up">
              {holding.target_price != null ? formatMoney(holding.target_price, currency) : "—"}
            </span>
          </div>
          {holding.buy_low != null && holding.buy_high != null && (
            <div className="row">
              <span className="muted">加仓区间</span>
              <span>
                {formatMoney(holding.buy_low, currency)} ~ {formatMoney(holding.buy_high, currency)}
              </span>
            </div>
          )}
          {holding.levels_note && <p className="muted">{holding.levels_note}</p>}
        </div>
      )}

      {holding.order && (
        <div className="card">
          <div className="section-title">今日操作</div>
          <div className="holding-action-line">{formatActionDetail(holding)}</div>
          {holding.order.legs?.length ? (
            <div className="muted order-preview">{formatOrder(holding)}</div>
          ) : null}
          <p className="muted pre-wrap">{holding.order.note}</p>
        </div>
      )}

      <form className="card" onSubmit={handleSave}>
        <div className="section-title">修改持仓</div>
        <p className="muted">股数与成本会保存；止损/目标每日根据行情自动计算。</p>
        <label className="field">
          <span>名称</span>
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </label>
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
        {saved && <p className="up">已保存到数据库</p>}
        {error && <p className="error">{error}</p>}
      </form>

      <button className="btn btn-danger" type="button" onClick={handleDelete} disabled={deleting}>
        {deleting ? "删除中…" : "删除持仓"}
      </button>
    </div>
  );
}
