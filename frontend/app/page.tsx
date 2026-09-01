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
  posted_at?: string;
  location_category: string;
  llm_fit_score?: number | null;
  llm_verdict?: string | null;
  llm_role_family?: string | null;
};

type DescriptionSection = {
  title: string;
  lines: string[];
};

type JobDetail = JobCard & {
  description: string;
  country?: string | null;
  updated_at?: string | null;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  source_url: string;
  llm_match_reasons?: string | null;
  llm_reject_reasons?: string | null;
  llm_missing_skills?: string | null;
  llm_model?: string | null;
  llm_last_evaluated_at?: string | null;
  description_sections?: DescriptionSection[] | null;
};

type SummaryResponse = {
  window_hours: number;
  total_new_jobs: number;
  high_match_jobs: number;
  by_source: Array<{ source: string; count: number }>;
};

type OfficialSourcesResponse = {
  sources: Array<{
    source_id: string;
    enabled: boolean;
    operational: boolean;
    wave?: number;
  }>;
};

function buildDirectBackendBase(): string {
  if (typeof window !== "undefined" && window.location?.hostname) {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  return "http://localhost:8000";
}

function normalizeBase(base: string): string {
  return (base || "").trim().replace(/\/+$/, "");
}

function apiBaseCandidates(): string[] {
  const direct = normalizeBase(buildDirectBackendBase());
  const localhost = "http://localhost:8000";
  const loopback = "http://127.0.0.1:8000";
  const proxied = "/api/backend";
  return Array.from(new Set([direct, localhost, loopback, proxied].map(normalizeBase).filter(Boolean)));
}

async function sleep(ms: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchJsonWithFallback<T>(path: string, params?: URLSearchParams): Promise<T | null> {
  const query = params?.toString();
  const suffix = query ? `${path}?${query}` : path;
  const retryDelaysMs = [300, 900];
  const candidates = apiBaseCandidates();

  for (let attempt = 0; attempt <= retryDelaysMs.length; attempt += 1) {
    for (const base of candidates) {
      const target = `${base}${suffix}`;
      try {
        const response = await fetch(target, { cache: "no-store" });
        if (!response.ok) {
          continue;
        }
        const contentType = (response.headers.get("content-type") || "").toLowerCase();
        if (!contentType.includes("application/json")) {
          // Avoid parsing HTML error pages as JSON.
          continue;
        }
        return (await response.json()) as T;
      } catch {
        continue;
      }
    }
    if (attempt < retryDelaysMs.length) {
      await sleep(retryDelaysMs[attempt]);
    }
  }
  return null;
}

export default function HomePage() {
  const [jobs, setJobs] = useState<JobCard[]>([]);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [officialSources, setOfficialSources] = useState<string[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [query, setQuery] = useState("");
  const [source, setSource] = useState("");
  const [minScore, setMinScore] = useState(0);
  const [minLlmScore, setMinLlmScore] = useState("60");
  const [aiPrecisionMode, setAiPrecisionMode] = useState(true);
  const [limit, setLimit] = useState(500);
  const [locationCategory, setLocationCategory] = useState("");
  const [selectedJob, setSelectedJob] = useState<JobDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const loadJobs = async () => {
    const params = new URLSearchParams();
    params.set("limit", String(limit));
    params.set("min_score", aiPrecisionMode ? "0" : String(minScore));
    if (query.trim()) {
      params.set("q", query.trim());
    }
    if (source) {
      params.set("source", source);
    }
    if (locationCategory) {
      params.set("location_category", locationCategory);
    }
    if (aiPrecisionMode) {
      params.set("llm_verdict", "strong_fit,possible_fit");
      if (minLlmScore) {
        params.set("min_llm_score", minLlmScore);
      }
    } else if (minLlmScore) {
      params.set("min_llm_score", minLlmScore);
    }
    try {
      const payload = await fetchJsonWithFallback<JobCard[]>("/jobs", params);
      if (!payload) {
        setJobs([]);
        return;
      }
      setJobs(payload);
    } catch {
      setJobs([]);
    }
  };

  const loadSummary = async () => {
    try {
      const payload = await fetchJsonWithFallback<SummaryResponse>("/jobs/summary/last-24h");
      if (!payload) {
        setSummary(null);
        return;
      }
      setSummary(payload);
    } catch {
      setSummary(null);
    }
  };

  const loadCount = async () => {
    const params = new URLSearchParams();
    params.set("min_score", aiPrecisionMode ? "0" : String(minScore));
    if (query.trim()) {
      params.set("q", query.trim());
    }
    if (source) {
      params.set("source", source);
    }
    if (locationCategory) {
      params.set("location_category", locationCategory);
    }
    if (aiPrecisionMode) {
      params.set("llm_verdict", "strong_fit,possible_fit");
      if (minLlmScore) {
        params.set("min_llm_score", minLlmScore);
      }
    } else if (minLlmScore) {
      params.set("min_llm_score", minLlmScore);
    }
    try {
      const payload = await fetchJsonWithFallback<{ total?: number }>("/jobs/count", params);
      setTotalCount(Number(payload?.total || 0));
    } catch {
      setTotalCount(0);
    }
  };

  const loadOfficialSources = async () => {
    try {
      const payload = await fetchJsonWithFallback<OfficialSourcesResponse>("/sources/official");
      if (!payload) {
        setOfficialSources([]);
        return;
      }
      const sourceNames = payload.sources
        .map((item) => `official_${item.source_id}`);
      setOfficialSources(sourceNames);
    } catch {
      setOfficialSources([]);
    }
  };

  const loadJobDetail = async (jobId: number) => {
    setDetailLoading(true);
    try {
      const payload = await fetchJsonWithFallback<JobDetail>(`/jobs/${jobId}`);
      if (!payload) {
        setSelectedJob(null);
        return;
      }
      setSelectedJob(payload);
    } catch {
      setSelectedJob(null);
    } finally {
      setDetailLoading(false);
    }
  };

  useEffect(() => {
    const load = async () => {
      await Promise.all([loadJobs(), loadSummary(), loadCount()]);
    };
    void load();
  }, [query, source, minScore, minLlmScore, aiPrecisionMode, limit, locationCategory]);

  useEffect(() => {
    void loadOfficialSources();
  }, []);

  const highMatchCount = useMemo(() => jobs.filter((job) => job.match_score >= 80).length, [jobs]);
  const rssBase = useMemo(() => buildDirectBackendBase(), []);
  const sourceOptions = useMemo(() => {
    const fromJobs = jobs.map((job) => job.source);
    const fromSummary = summary?.by_source.map((item) => item.source) ?? [];
    return Array.from(new Set([...fromJobs, ...fromSummary, ...officialSources])).sort();
  }, [jobs, summary, officialSources]);

  return (
    <main className="page">
      <section className="hero glass">
        <h1>JobsRSS Intelligence</h1>
        <p>Cloud and security opportunities ranked for your profile.</p>
        <div className="actions">
          <a className="button primary" href={`${rssBase}/rss/high-match.xml`} target="_blank">
            High Match RSS
          </a>
          <a className="button" href={`${rssBase}/rss/all.xml`} target="_blank">
            All Jobs RSS
          </a>
        </div>
      </section>

      <section className="stats">
        <div className="stat glass">
          <span>Total Loaded</span>
          <strong>{totalCount}</strong>
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
          <label>AI Precision Mode</label>
          <select
            value={aiPrecisionMode ? "on" : "off"}
            onChange={(event) => {
              const enabled = event.target.value === "on";
              setAiPrecisionMode(enabled);
              if (enabled) {
                setMinScore(0);
                if (!minLlmScore) {
                  setMinLlmScore("60");
                }
              }
            }}
          >
            <option value="on">On (AI-only final filter)</option>
            <option value="off">Off (manual rule + AI mix)</option>
          </select>
        </div>
        <div className="field">
          <label>Rule Score</label>
          <select
            disabled={aiPrecisionMode}
            value={String(minScore)}
            onChange={(event) => setMinScore(Number(event.target.value))}
          >
            <option value="0">0</option>
            <option value="60">60</option>
            <option value="80">80</option>
          </select>
        </div>
        <div className="field">
          <label>Fetch Limit</label>
          <select value={String(limit)} onChange={(event) => setLimit(Number(event.target.value))}>
            <option value="50">50</option>
            <option value="100">100</option>
            <option value="200">200</option>
            <option value="500">500</option>
          </select>
        </div>
        <div className="field">
          <label>AI Score</label>
          <select
            value={minLlmScore}
            onChange={(event) => setMinLlmScore(event.target.value)}
          >
            <option value="">All</option>
            <option value="60">60</option>
            <option value="70">70</option>
            <option value="80">80</option>
          </select>
        </div>
        <div className="field">
          <label>Location Classification</label>
          <select
            value={locationCategory}
            onChange={(event) => setLocationCategory(event.target.value)}
          >
            <option value="">All</option>
            <option value="confirmed_shanghai">Confirmed Shanghai</option>
            <option value="unclassified">Unclassified</option>
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
          <div className="empty glass">
            No jobs matched current filters. Try setting AI Score to All or turning AI Precision Mode Off.
          </div>
        ) : (
          jobs.map((job) => (
            <article key={job.id} className="job-card glass">
              <div>
                <p className="job-company">{job.company}</p>
                <h2>{job.title}</h2>
                <p className="job-meta">
                  {job.location} · {job.source}
                </p>
                {job.llm_fit_score != null && (
                  <p className="job-meta">
                    LLM Fit: {Math.round(job.llm_fit_score)} ({job.llm_verdict || "n/a"})
                  </p>
                )}
                <span className="location-badge">
                  {job.location_category === "confirmed_shanghai"
                    ? "Shanghai"
                    : "Location unclassified"}
                </span>
                {job.posted_at && <p className="job-meta">Posted: {new Date(job.posted_at).toLocaleString()}</p>}
              </div>
              <div className="job-right">
                <span className="score">
                  {job.llm_fit_score != null ? `AI ${Math.round(job.llm_fit_score)}` : `Rule ${Math.round(job.match_score)}`}
                </span>
                <a className="button small" href={job.apply_url} target="_blank">
                  Apply Now
                </a>
                <button className="button small detail-btn" onClick={() => void loadJobDetail(job.id)}>
                  View Details
                </button>
              </div>
            </article>
          ))
        )}
      </section>

      {(selectedJob || detailLoading) && (
        <section className="detail-overlay" onClick={() => setSelectedJob(null)}>
          <article className="detail-panel glass" onClick={(event) => event.stopPropagation()}>
            {detailLoading || !selectedJob ? (
              <p className="detail-loading">Loading full job details...</p>
            ) : (
              <>
                <div className="detail-header">
                  <div>
                    <p className="job-company">{selectedJob.company}</p>
                    <h2>{selectedJob.title}</h2>
                    <p className="job-meta">
                      {selectedJob.location} · {selectedJob.source}
                    </p>
                  </div>
                  <button className="button small detail-close" onClick={() => setSelectedJob(null)}>
                    Close
                  </button>
                </div>
                <div className="detail-actions">
                  <a className="button small primary" href={selectedJob.apply_url} target="_blank">
                    Apply Now
                  </a>
                  <a className="button small" href={selectedJob.source_url} target="_blank">
                    Open Source
                  </a>
                </div>
                <div className="detail-description">
                  <h3>Description</h3>
                  {selectedJob.description_sections && selectedJob.description_sections.length > 0 ? (
                    <div className="description-sections">
                      {selectedJob.description_sections.map((section, index) => (
                        <section key={`${section.title}-${index}`} className="description-section">
                          <h4>{section.title}</h4>
                          <ul>
                            {section.lines.map((line, lineIndex) => (
                              <li key={`${index}-${lineIndex}`}>{line}</li>
                            ))}
                          </ul>
                        </section>
                      ))}
                    </div>
                  ) : (
                    <p>{selectedJob.description || "No description available."}</p>
                  )}
                </div>
                {selectedJob.llm_match_reasons && (
                  <div className="detail-description">
                    <h3>LLM Match Reasons</h3>
                    <p>{selectedJob.llm_match_reasons}</p>
                  </div>
                )}
                {selectedJob.llm_reject_reasons && (
                  <div className="detail-description">
                    <h3>LLM Reject Reasons</h3>
                    <p>{selectedJob.llm_reject_reasons}</p>
                  </div>
                )}
              </>
            )}
          </article>
        </section>
      )}
    </main>
  );
}
