import { useCallback, useEffect, useState } from "react";
import { api, Brief } from "../api";

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
          <div className="card highlight">
            <div className="section-title">今日结论</div>
            <p>{brief.conclusion}</p>
            <p className="muted">{new Date(brief.generated_at).toLocaleString()}</p>
          </div>
          {brief.sections.map((section) => (
            <div className="card" key={section.title}>
              <div className="section-title">{section.title}</div>
              <div className="pre-wrap markdown-lite">
                {section.lines
                  .filter((line) => line && !line.startsWith("| **") && line !== "| --- | --- | --- | --- | --- |")
                  .join("\n")}
              </div>
            </div>
          ))}
          <button className="btn btn-secondary" onClick={() => setShowFull((v) => !v)}>
            {showFull ? "收起完整简报" : "查看完整 Markdown"}
          </button>
          {showFull && (
            <div className="card markdown-lite pre-wrap">{brief.markdown}</div>
          )}
        </>
      )}
    </div>
  );
}
