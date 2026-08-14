"use client";

import { useEffect, useMemo, useState } from "react";

type JobCard = {
  id: number;
  company: string;
  title: string;
  location: string;
  match_score: number;
  apply_url: string;
  source: string;
};

type SummaryResponse = {
  window_hours: number;
  total_new_jobs: number;
  high_match_jobs: number;
  by_source: Array<{ source: string; count: number }>;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export default function HomePage() {
  const [jobs, setJobs] = useState<JobCard[]>([]);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [query, setQuery] = useState("");
  const [source, setSource] = useState("");
  const [minScore, setMinScore] = useState(0);

  const loadJobs = async () => {
    const params = new URLSearchParams();
    params.set("limit", "50");
    params.set("min_score", String(minScore));
    if (query.trim()) {
      params.set("q", query.trim());
    }
    if (source) {
      params.set("source", source);
    }
    try {
      const response = await fetch(`${API_BASE}/jobs?${params.toString()}`, { cache: "no-store" });
      if (!response.ok) {
        setJobs([]);
        return;
      }
      const payload: JobCard[] = await response.json();
      setJobs(payload);
    } catch {
      setJobs([]);
    }
  };

  const loadSummary = async () => {
    try {
      const response = await fetch(`${API_BASE}/jobs/summary/last-24h`, { cache: "no-store" });
      if (!response.ok) {
        setSummary(null);
        return;
      }
      const payload: SummaryResponse = await response.json();
      setSummary(payload);
    } catch {
      setSummary(null);
    }
  };

  useEffect(() => {
    const load = async () => {
      await Promise.all([loadJobs(), loadSummary()]);
    };
    void load();
  }, [query, source, minScore]);

  const highMatchCount = useMemo(() => jobs.filter((job) => job.match_score >= 80).length, [jobs]);
  const sourceOptions = useMemo(() => Array.from(new Set(jobs.map((job) => job.source))).sort(), [jobs]);

  return (
    <main className="page">
      <section className="hero glass">
        <h1>JobsRSS Intelligence</h1>
        <p>Cloud and security opportunities ranked for your profile.</p>
        <div className="actions">
          <a className="button primary" href={`${API_BASE}/rss/high-match.xml`} target="_blank">
            High Match RSS
          </a>
          <a className="button" href={`${API_BASE}/rss/all.xml`} target="_blank">
            All Jobs RSS
          </a>
        </div>
      </section>

      <section className="stats">
        <div className="stat glass">
          <span>Total Loaded</span>
          <strong>{jobs.length}</strong>
        </div>
        <div className="stat glass">
          <span>High Match (80+)</span>
          <strong>{highMatchCount}</strong>
        </div>
        <div className="stat glass">
          <span>Last 24h New</span>
          <strong>{summary?.total_new_jobs ?? 0}</strong>
        </div>
        <div className="stat glass">
          <span>Last 24h High Match</span>
          <strong>{summary?.high_match_jobs ?? 0}</strong>
        </div>
      </section>

      <section className="glass filters">
        <div className="field">
          <label>Search</label>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="cloud security / architect / devsecops"
          />
        </div>
        <div className="field">
          <label>Source</label>
          <select value={source} onChange={(event) => setSource(event.target.value)}>
            <option value="">All sources</option>
            {sourceOptions.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>Min Score</label>
          <select value={String(minScore)} onChange={(event) => setMinScore(Number(event.target.value))}>
            <option value="0">0</option>
            <option value="60">60</option>
            <option value="80">80</option>
          </select>
        </div>
      </section>

      {summary && summary.by_source.length > 0 && (
        <section className="glass source-summary">
          <h3>24h Source Distribution</h3>
          <div className="chips">
            {summary.by_source.map((item) => (
              <span key={item.source} className="chip">
                {item.source}: {item.count}
              </span>
            ))}
          </div>
        </section>
      )}

      <section className="job-list">
        {jobs.length === 0 ? (
          <div className="empty glass">No jobs available yet. Start collectors from the worker service.</div>
        ) : (
          jobs.map((job) => (
            <article key={job.id} className="job-card glass">
              <div>
                <p className="job-company">{job.company}</p>
                <h2>{job.title}</h2>
                <p className="job-meta">
                  {job.location} · {job.source}
                </p>
              </div>
              <div className="job-right">
                <span className="score">{Math.round(job.match_score)}</span>
                <a className="button small" href={job.apply_url} target="_blank">
                  Apply Now
                </a>
              </div>
            </article>
          ))
        )}
      </section>
    </main>
  );
}
