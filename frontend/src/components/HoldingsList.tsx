import { Link } from "react-router-dom";
import { changeClass, formatMoney, formatOrder, Holding } from "../api";

type Props = {
  items: Holding[];
};

export default function HoldingsList({ items }: Props) {
  if (items.length === 0) {
    return <p className="muted">暂无持仓，请在 portfolio_config.json 配置后刷新。</p>;
  }

  return (
    <div className="stack">
      {items.map((item) => (
        <Link key={item.ticker} to={`/holding/${encodeURIComponent(item.ticker)}`} className="card link-card">
          <div className="row">
            <div>
              <div className="title">{item.name}</div>
              <div className="muted">{item.ticker} · {item.market}</div>
            </div>
            <div className="text-right">
              {item.price != null ? (
                <>
                  <div>{formatMoney(item.price, item.currency || "USD")}</div>
                  <div className={changeClass(item.change_pct)}>
                    {item.change_pct != null ? `${item.change_pct >= 0 ? "+" : ""}${item.change_pct.toFixed(2)}%` : "—"}
                  </div>
                </>
              ) : (
                <span className="muted">行情异常</span>
              )}
            </div>
          </div>
          <div className="row meta">
            <span className={`pill pill-${item.portfolio_action}`}>{item.portfolio_action}</span>
            {item.pnl_pct != null && (
              <span className={changeClass(item.pnl_pct)}>
                {item.pnl_pct >= 0 ? "+" : ""}
                {item.pnl_pct.toFixed(1)}%
              </span>
            )}
          </div>
          {item.order && item.order.side !== "观望" && (
            <div className="muted order-preview">
              {item.order.side} · {formatOrder(item)}
            </div>
          )}
        </Link>
      ))}
    </div>
  );
}
