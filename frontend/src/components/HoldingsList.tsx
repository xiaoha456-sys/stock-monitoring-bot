import { Link } from "react-router-dom";
import { changeClass, formatActionDetail, formatMoney, Holding } from "../api";

const MARKET_ORDER = ["US", "CN", "AU"] as const;
const MARKET_LABELS: Record<string, string> = {
  US: "美股",
  CN: "A股",
  AU: "澳股",
};

type Props = {
  items: Holding[];
};

function orderTone(side: string | undefined) {
  if (side === "买入") return "brief-badge-positive";
  if (side === "卖出") return "brief-badge-negative";
  return "brief-badge-neutral";
}

export default function HoldingsList({ items }: Props) {
  if (items.length === 0) {
    return <p className="muted">暂无持仓，请在 portfolio_config.json 配置后刷新。</p>;
  }

  const byMarket = MARKET_ORDER.map((market) => ({
    market,
    label: MARKET_LABELS[market] || market,
    items: items
      .filter((item) => item.market === market)
      .sort((a, b) => (b.weight_pct ?? 0) - (a.weight_pct ?? 0)),
  })).filter((group) => group.items.length > 0);

  return (
    <div className="stack">
      {byMarket.map((group) => (
        <div key={group.market}>
          <div className="today-market-label">{group.label}</div>
          <div className="stack">
            {group.items.map((item) => {
              const currency = item.currency || "USD";
              const side = item.order?.side || "观望";
              const actionDetail = formatActionDetail(item);
              return (
                <Link
                  key={item.ticker}
                  to={`/holding/${encodeURIComponent(item.ticker)}`}
                  className="card link-card holding-card"
                >
                  <div className="row">
                    <div>
                      <div className="title">{item.name}</div>
                      <div className="muted">{item.ticker}</div>
                    </div>
                    <div className="text-right">
                      {item.price != null ? (
                        <>
                          <div>{formatMoney(item.price, currency)}</div>
                          <div className={changeClass(item.change_pct)}>
                            {item.change_pct != null
                              ? `${item.change_pct >= 0 ? "+" : ""}${item.change_pct.toFixed(2)}%`
                              : "—"}
                          </div>
                        </>
                      ) : (
                        <span className="muted">行情异常</span>
                      )}
                    </div>
                  </div>

                  <div className="row meta">
                    <span className={`pill pill-${item.portfolio_action}`}>{item.portfolio_action}</span>
                    <span className={`brief-badge ${orderTone(side)}`}>{side}</span>
                    {item.pnl_pct != null && (
                      <span className={changeClass(item.pnl_pct)}>
                        浮盈 {item.pnl_pct >= 0 ? "+" : ""}
                        {item.pnl_pct.toFixed(1)}%
                      </span>
                    )}
                    {item.weight_pct != null && (
                      <span className="muted">仓位 {item.weight_pct.toFixed(1)}%</span>
                    )}
                  </div>

                  <div className="holding-action-line">{actionDetail}</div>

                  {item.stop_loss != null && item.target_price != null && (
                    <div className="muted order-preview">
                      止损 {formatMoney(item.stop_loss, currency)} · 目标{" "}
                      {formatMoney(item.target_price, currency)}
                    </div>
                  )}
                </Link>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
