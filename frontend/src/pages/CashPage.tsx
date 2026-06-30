import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, MarketCash } from "../api";

const MODES = [
  { value: "deploy", label: "可加仓 / 新开仓" },
  { value: "rotate_only", label: "仅减仓置换" },
];

export default function CashPage() {
  const [items, setItems] = useState<MarketCash[]>([]);
  const [drafts, setDrafts] = useState<Record<string, { available: string; mode: string; note: string }>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await api.listCash();
      setItems(data);
      const next: Record<string, { available: string; mode: string; note: string }> = {};
      for (const row of data) {
        next[row.market] = {
          available: String(row.available),
          mode: row.mode,
          note: row.note || "",
        };
      }
      setDrafts(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleSave(e: FormEvent, market: string) {
    e.preventDefault();
    const draft = drafts[market];
    if (!draft) return;
    setSaving(market);
    setError("");
    setSaved(null);
    try {
      const updated = await api.updateCash(market, {
        available: Number(draft.available),
        mode: draft.mode,
        note: draft.note.trim() || undefined,
      });
      setItems((prev) => prev.map((row) => (row.market === market ? updated : row)));
      setSaved(market);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(null);
    }
  }

  function updateDraft(market: string, patch: Partial<{ available: string; mode: string; note: string }>) {
    setDrafts((prev) => ({
      ...prev,
      [market]: { ...prev[market], ...patch },
    }));
  }

  return (
    <div>
      <div className="page-header">
        <h1>资金</h1>
        <button className="btn btn-secondary" onClick={load} disabled={loading}>
          刷新
        </button>
      </div>
      <p className="muted">各市场剩余可用资金，保存后影响挂单与加仓建议。</p>
      {error && <div className="error">{error}</div>}
      {loading ? (
        <p className="muted">加载中…</p>
      ) : (
        <div className="stack">
          {items.map((row) => {
            const draft = drafts[row.market];
            if (!draft) return null;
            return (
              <form className="card" key={row.market} onSubmit={(e) => handleSave(e, row.market)}>
                <div className="row">
                  <div className="title">{row.label}</div>
                  <span className="muted">{row.currency}</span>
                </div>
                <label className="field">
                  <span>可用金额</span>
                  <input
                    inputMode="decimal"
                    value={draft.available}
                    onChange={(e) => updateDraft(row.market, { available: e.target.value })}
                  />
                </label>
                <label className="field">
                  <span>操作模式</span>
                  <select value={draft.mode} onChange={(e) => updateDraft(row.market, { mode: e.target.value })}>
                    {MODES.map((mode) => (
                      <option key={mode.value} value={mode.value}>
                        {mode.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>备注</span>
                  <input value={draft.note} onChange={(e) => updateDraft(row.market, { note: e.target.value })} />
                </label>
                <button className="btn" type="submit" disabled={saving === row.market}>
                  {saving === row.market ? "保存中…" : "保存"}
                </button>
                {saved === row.market && <p className="up">已保存</p>}
              </form>
            );
          })}
        </div>
      )}
    </div>
  );
}
