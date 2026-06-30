import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";

const MARKETS = [
  { value: "US", label: "美股" },
  { value: "CN", label: "A股" },
  { value: "AU", label: "澳股" },
];

export default function AddHoldingPage() {
  const navigate = useNavigate();
  const [ticker, setTicker] = useState("");
  const [market, setMarket] = useState("US");
  const [name, setName] = useState("");
  const [shares, setShares] = useState("");
  const [cost, setCost] = useState("");
  const [stop, setStop] = useState("");
  const [target, setTarget] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!ticker.trim()) {
      setError("请填写股票代码");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const body: Parameters<typeof api.createHolding>[0] = {
        ticker: ticker.trim(),
        market,
      };
      if (name.trim()) body.name = name.trim();
      if (shares.trim()) body.shares = Number(shares);
      if (cost.trim()) body.cost_basis = Number(cost);
      if (stop.trim()) body.stop_loss = Number(stop);
      if (target.trim()) body.target_price = Number(target);
      const created = await api.createHolding(body);
      navigate(`/holding/${encodeURIComponent(created.ticker)}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "添加失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <Link to="/" className="muted back-link">
        ← 返回持仓
      </Link>
      <h1>添加持仓</h1>
      <p className="muted">保存到服务器数据库，手机与电脑同步。</p>

      <form className="card" onSubmit={handleSubmit}>
        <label className="field">
          <span>代码 *</span>
          <input
            placeholder="RKLB / 588000.SS / WTC.AX"
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            autoCapitalize="characters"
          />
        </label>
        <label className="field">
          <span>市场 *</span>
          <select value={market} onChange={(e) => setMarket(e.target.value)}>
            {MARKETS.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>
        </label>
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
        <label className="field">
          <span>止损</span>
          <input inputMode="decimal" value={stop} onChange={(e) => setStop(e.target.value)} />
        </label>
        <label className="field">
          <span>目标价</span>
          <input inputMode="decimal" value={target} onChange={(e) => setTarget(e.target.value)} />
        </label>
        <button className="btn" type="submit" disabled={saving}>
          {saving ? "保存中…" : "添加"}
        </button>
        {error && <p className="error">{error}</p>}
      </form>
    </div>
  );
}
