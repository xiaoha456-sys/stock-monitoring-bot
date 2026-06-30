import { useCallback, useEffect, useState } from "react";
import { api, Brief, BriefRow, BriefSection } from "../api";

function toneClass(tone: string) {
  if (tone === "positive") return "brief-badge-positive";
  if (tone === "negative") return "brief-badge-negative";
  if (tone === "warn") return "brief-badge-warn";
  return "brief-badge-neutral";
}

function SectionBlock({ section }: { section: BriefSection }) {
  const isMarketHeader = (row: BriefRow) =>
    row.badge === "" && row.detail === "" && row.secondary === "" && row.subdetail === "";

  return (
    <div className="card brief-section">
      <div className="brief-section-head">
        <div className="section-title">{section.title}</div>
        {section.subtitle && <p className="muted brief-subtitle">{section.subtitle}</p>}
      </div>

      {section.kind === "rows" && (section.rows?.length ?? 0) > 0 && (
        <div className="brief-rows">
          {section.rows!.map((row, index) =>
            isMarketHeader(row) ? (
              <div key={`${row.primary}-${index}`} className="brief-market-label">
                {row.primary}
              </div>
            ) : (
              <div key={`${row.primary}-${index}`} className="brief-row">
                <div className="brief-row-main">
                  <div className="brief-row-title">{row.primary}</div>
                  {row.secondary && <div className="muted brief-row-meta">{row.secondary}</div>}
                </div>
                {row.badge && (
                  <span className={`brief-badge ${toneClass(row.badge_tone)}`}>{row.badge}</span>
                )}
                {(row.detail || row.subdetail) && (
                  <div className="brief-row-detail">
                    {row.detail && <div>{row.detail}</div>}
                    {row.subdetail && <div className="muted">{row.subdetail}</div>}
                  </div>
                )}
              </div>
            ),
          )}
        </div>
      )}

      {section.kind === "text" && (section.lines?.length ?? 0) > 0 && (
        <ul className="brief-list">
          {section.lines!.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function BriefPage() {
  const [brief, setBrief] = useState<Brief | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showFull, setShowFull] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setBrief(await api.todayBrief());
    } catch (err) {
      setError(err instanceof Error ? err.message : "简报生成失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div>
      <div className="page-header">
        <h1>简报</h1>
        <button className="btn btn-secondary" onClick={load} disabled={loading}>
          刷新
        </button>
      </div>
      {loading && <p className="muted">生成简报中（约 30–60 秒）…</p>}
      {error && <div className="error">{error}</div>}
      {brief && (
        <>
          <div className="card highlight brief-conclusion">
            <div className="section-title">今日结论</div>
            {brief.conclusion_items && brief.conclusion_items.length > 0 ? (
              <ul className="brief-conclusion-list">
                {brief.conclusion_items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : (
              <p>{brief.conclusion}</p>
            )}
            <p className="muted brief-time">
              {new Date(brief.generated_at).toLocaleString()}
            </p>
          </div>

          {brief.sections.map((section) => (
            <SectionBlock key={section.title} section={section} />
          ))}

          <button className="btn btn-secondary brief-full-toggle" onClick={() => setShowFull((v) => !v)}>
            {showFull ? "收起完整简报" : "查看完整邮件版"}
          </button>
          {showFull && (
            <div className="card markdown-lite pre-wrap brief-markdown">{brief.markdown}</div>
          )}
        </>
      )}
    </div>
  );
}
