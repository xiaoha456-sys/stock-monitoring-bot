import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import HoldingsList from "../components/HoldingsList";

export default function HoldingsPage() {
  const [items, setItems] = useState<Awaited<ReturnType<typeof api.listHoldings>>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [elapsed, setElapsed] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    setElapsed(0);
    const started = Date.now();
    const timer = window.setInterval(() => {
      setElapsed(Math.floor((Date.now() - started) / 1000));
    }, 1000);
    try {
      setItems(await api.listHoldings());
    } catch (err) {
      setItems([]);
      const message = err instanceof Error ? err.message : "加载失败";
      setError(
        message.includes("fetch")
          ? "无法连接 API。请确认已运行 ./scripts/dev.sh，电脑浏览器用 http://127.0.0.1:5173；手机需配置 VITE_API_BASE。"
          : message
      );
    } finally {
      window.clearInterval(timer);
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div>
      <div className="page-header">
        <h1>持仓</h1>
        <div className="header-actions">
          <Link to="/holding/new" className="btn btn-secondary">
            添加
          </Link>
          <button className="btn btn-secondary" onClick={load} disabled={loading}>
            刷新
          </button>
        </div>
      </div>
      {error && <div className="error">{error}</div>}
      {loading ? (
        <div className="stack">
          <p className="muted">
            正在拉取行情与挂单… 约需 10–20 秒{elapsed > 0 ? `（已等待 ${elapsed}s）` : ""}
          </p>
          {[1, 2, 3].map((key) => (
            <div className="card skeleton" key={key} aria-hidden>
              <div className="skeleton-line wide" />
              <div className="skeleton-line" />
              <div className="skeleton-line short" />
            </div>
          ))}
        </div>
      ) : (
        <HoldingsList items={items} />
      )}
    </div>
  );
}
