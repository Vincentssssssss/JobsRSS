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
  status?: string;
  favorited_at?: string | null;
  applied_at?: string | null;
  last_viewed_at?: string | null;
  view_count?: number;
};

type MarkUpdate = { favorited?: boolean; applied?: boolean };

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
  total?: number;
  sources: Array<{
    source_id: string;
    enabled: boolean;
    operational: boolean;
    wave?: number;
  }>;
};

type SourceCountsResponse = {
  counts: Array<{
    source: string;
    count: number;
  }>;
};

const LOCATION_BADGES: Record<string, string> = {
  confirmed_shanghai: "Shanghai",
  confirmed_yangtze_delta: "Jiangsu/Zhejiang",
  confirmed_hong_kong: "Hong Kong",
  confirmed_malaysia: "Malaysia",
  confirmed_southeast_asia: "Southeast Asia",
};

function buildDirectBackendBase(): string {
  if (typeof window !== "undefined" && window.location?.hostname) {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  return "http://localhost:8000";
}

function buildPublicBase(): string {
  if (typeof window === "undefined") {
    return "http://localhost:8000";
  }
  const { hostname, protocol, origin } = window.location;
  if (isLocalHostname(hostname)) {
    return `${protocol}//${hostname}:8000`;
  }
  return origin;
}

function normalizeBase(base: string): string {
  return (base || "").trim().replace(/\/+$/, "");
}

function isLocalHostname(hostname: string): boolean {
  return hostname === "localhost" || hostname === "127.0.0.1";
}

// Same-origin API paths only exist behind the GKE Gateway; locally they 404 before
// the proxy answers. Remembering the base that worked avoids that on every request.
let workingApiBase: string | null = null;

function apiBaseCandidates(): string[] {
  const sameOrigin = "";
  const proxied = "/api/backend";
  const preferred = workingApiBase === null ? [] : [workingApiBase];
  if (typeof window !== "undefined" && !isLocalHostname(window.location.hostname)) {
    // GKE Gateway only listens on :80/:443. :8000 hangs for tens of seconds.
    return Array.from(new Set([...preferred, sameOrigin, proxied]));
  }
  const direct = normalizeBase(buildDirectBackendBase());
  const localhost = "http://localhost:8000";
  const loopback = "http://127.0.0.1:8000";
  return Array.from(new Set([...preferred, sameOrigin, proxied, direct, localhost, loopback]));
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
        const response = await fetch(target, {
          cache: "no-store",
          signal: AbortSignal.timeout(2500),
        });
        if (!response.ok) {
          continue;
        }
        const contentType = (response.headers.get("content-type") || "").toLowerCase();
        if (!contentType.includes("application/json")) {
          // Avoid parsing HTML error pages as JSON.
          continue;
        }
        const payload = (await response.json()) as T;
        workingApiBase = base;
        return payload;
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

// Writes are tried once per base and never retried: a timed-out POST /view may already have counted.
async function sendJsonWithFallback<T>(method: "POST" | "PUT", path: string, body?: unknown): Promise<T | null> {
  for (const base of apiBaseCandidates()) {
    try {
      const response = await fetch(`${base}${path}`, {
        method,
        cache: "no-store",
        headers: body === undefined ? undefined : { "content-type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: AbortSignal.timeout(4000),
      });
      const contentType = (response.headers.get("content-type") || "").toLowerCase();
      if (!response.ok || !contentType.includes("application/json")) {
        continue;
      }
      const payload = (await response.json()) as T;
      workingApiBase = base;
      return payload;
    } catch {
      continue;
    }
  }
  return null;
}

function formatShortTime(value: string): string {
  return new Date(value).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const SAVED_MARK_FILTERS = new Set(["favorited", "applied"]);

export default function HomePage() {
  const [jobs, setJobs] = useState<JobCard[]>([]);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [officialSources, setOfficialSources] = useState<string[]>([]);
  const [officialSourceTotal, setOfficialSourceTotal] = useState<number | null>(null);
  const [officialSourceLoadError, setOfficialSourceLoadError] = useState(false);
  const [sourceCounts, setSourceCounts] = useState<Record<string, number>>({});
  const [sourceCountsLoaded, setSourceCountsLoaded] = useState(false);
  const [sourceCountsLoadError, setSourceCountsLoadError] = useState(false);
  const [totalCount, setTotalCount] = useState(0);
  const [query, setQuery] = useState("");
  const [source, setSource] = useState("");
  const [minScore, setMinScore] = useState(0);
  const [minLlmScore, setMinLlmScore] = useState("60");
  const [aiPrecisionMode, setAiPrecisionMode] = useState(true);
  const [limit, setLimit] = useState(500);
  const [locationCategory, setLocationCategory] = useState("");
  const [markFilter, setMarkFilter] = useState("");
  const [pendingMarks, setPendingMarks] = useState<Record<number, boolean>>({});
  const [selectedJob, setSelectedJob] = useState<JobDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [listLoading, setListLoading] = useState(true);
  const [filterRelaxed, setFilterRelaxed] = useState(false);
  const [inventoryCount, setInventoryCount] = useState(0);
  const [scoredCount, setScoredCount] = useState(0);

  // Favorites and applied jobs are a personal list: show them even if closed or below the AI filters.
  const savedMarkView = SAVED_MARK_FILTERS.has(markFilter);

  const buildJobParams = (requestedLlm: boolean, includeLimit: boolean): URLSearchParams => {
    const includeLlm = requestedLlm && !savedMarkView;
    const params = new URLSearchParams();
    if (includeLimit) {
      params.set("limit", String(limit));
    }
    if (markFilter) {
      params.set("mark", markFilter);
    }
    if (savedMarkView) {
      params.set("status", "");
    }
    params.set("min_score", aiPrecisionMode || !includeLlm ? "0" : String(minScore));
    if (query.trim()) {
      params.set("q", query.trim());
    }
    if (source) {
      params.set("source", source);
    }
    if (locationCategory) {
      params.set("location_category", locationCategory);
    }
    if (includeLlm) {
      if (aiPrecisionMode) {
        params.set("llm_verdict", "strong_fit,possible_fit");
        if (minLlmScore) {
          params.set("min_llm_score", minLlmScore);
        }
      } else if (minLlmScore) {
        params.set("min_llm_score", minLlmScore);
      }
    }
    return params;
  };

  const loadJobs = async (includeLlm: boolean) => {
    try {
      const payload = await fetchJsonWithFallback<JobCard[]>("/jobs", buildJobParams(includeLlm, true));
      if (!payload) {
        setJobs([]);
        return [];
      }
      setJobs(payload);
      return payload;
    } catch {
      setJobs([]);
      return [];
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

  const loadCount = async (includeLlm: boolean) => {
    try {
      const payload = await fetchJsonWithFallback<{ total?: number }>(
        "/jobs/count",
        buildJobParams(includeLlm, false),
      );
      const total = Number(payload?.total || 0);
      setTotalCount(total);
      return total;
    } catch {
      setTotalCount(0);
      return 0;
    }
  };

  const loadSourceCounts = async (includeLlm: boolean) => {
    const params = buildJobParams(includeLlm, false);
    params.delete("source");
    try {
      const payload = await fetchJsonWithFallback<SourceCountsResponse>("/jobs/source-counts", params);
      if (!payload) {
        setSourceCounts({});
        setSourceCountsLoaded(false);
        setSourceCountsLoadError(true);
        return;
      }
      const next: Record<string, number> = {};
      for (const item of payload.counts || []) {
        next[item.source] = Number(item.count || 0);
      }
      setSourceCounts(next);
      setSourceCountsLoaded(true);
      setSourceCountsLoadError(false);
    } catch {
      setSourceCounts({});
      setSourceCountsLoaded(false);
      setSourceCountsLoadError(true);
    }
  };

  const loadOfficialSources = async () => {
    try {
      const payload = await fetchJsonWithFallback<OfficialSourcesResponse>("/sources/official");
      if (!payload) {
        setOfficialSourceLoadError(true);
        return;
      }
      const sourceNames = payload.sources
        .map((item) => `official_${item.source_id}`);
      setOfficialSources(sourceNames);
      setOfficialSourceTotal(
        typeof payload.total === "number" ? payload.total : sourceNames.length,
      );
      setOfficialSourceLoadError(false);
    } catch {
      setOfficialSourceLoadError(true);
    }
  };

  const applyJobUpdate = (updated: JobCard) => {
    const pick = (job: JobCard) => ({
      status: updated.status,
      favorited_at: updated.favorited_at,
      applied_at: updated.applied_at,
      last_viewed_at: updated.last_viewed_at,
      view_count: updated.view_count,
    });
    setJobs((current) => current.map((job) => (job.id === updated.id ? { ...job, ...pick(updated) } : job)));
    setSelectedJob((current) => (current && current.id === updated.id ? { ...current, ...pick(updated) } : current));
  };

  const recordView = async (jobId: number) => {
    const updated = await sendJsonWithFallback<JobCard>("POST", `/jobs/${jobId}/view`);
    if (updated) {
      applyJobUpdate(updated);
    }
  };

  const toggleMark = async (job: JobCard, update: MarkUpdate) => {
    if (pendingMarks[job.id]) {
      return;
    }
    setPendingMarks((current) => ({ ...current, [job.id]: true }));
    try {
      const updated = await sendJsonWithFallback<JobCard>("PUT", `/jobs/${job.id}/marks`, update);
      if (updated) {
        applyJobUpdate(updated);
      } else {
        window.alert("Could not save the mark. Is the API container running?");
      }
    } finally {
      setPendingMarks((current) => {
        const next = { ...current };
        delete next[job.id];
        return next;
      });
    }
  };

  const renderMarkButtons = (job: JobCard) => (
    <>
      <button
        className={`button small mark-btn${job.favorited_at ? " active-favorite" : ""}`}
        disabled={Boolean(pendingMarks[job.id])}
        onClick={() => void toggleMark(job, { favorited: !job.favorited_at })}
        title={job.favorited_at ? `Favorited ${formatShortTime(job.favorited_at)}` : "Save to favorites"}
      >
        {job.favorited_at ? "★ Favorited" : "☆ Favorite"}
      </button>
      <button
        className={`button small mark-btn${job.applied_at ? " active-applied" : ""}`}
        disabled={Boolean(pendingMarks[job.id])}
        onClick={() => void toggleMark(job, { applied: !job.applied_at })}
        title={job.applied_at ? "Click to undo" : "Mark as applied"}
      >
        {job.applied_at ? "✓ Applied" : "Mark Applied"}
      </button>
    </>
  );

  const renderMarkBadges = (job: JobCard) => {
    const viewCount = job.view_count ?? 0;
    const closed = job.status != null && job.status !== "active";
    if (!job.applied_at && !job.favorited_at && !job.last_viewed_at && !closed) {
      return null;
    }
    return (
      <div className="mark-badges">
        {job.applied_at && <span className="mark-badge applied">Applied {formatShortTime(job.applied_at)}</span>}
        {job.favorited_at && <span className="mark-badge favorite">Favorited</span>}
        {job.last_viewed_at && (
          <span className="mark-badge viewed">
            Viewed {viewCount}× · last {formatShortTime(job.last_viewed_at)}
          </span>
        )}
        {closed && <span className="mark-badge closed">Closed</span>}
      </div>
    );
  };

  const loadJobDetail = async (jobId: number) => {
    setDetailLoading(true);
    const viewed = sendJsonWithFallback<JobCard>("POST", `/jobs/${jobId}/view`);
    try {
      const payload = await fetchJsonWithFallback<JobDetail>(`/jobs/${jobId}`);
      setSelectedJob(payload ?? null);
    } catch {
      setSelectedJob(null);
    } finally {
      setDetailLoading(false);
    }
    // Applied after the detail is set so the panel shows this view even if the GET raced ahead of it.
    const updated = await viewed;
    if (updated) {
      applyJobUpdate(updated);
    }
  };

  useEffect(() => {
    const load = async () => {
      setListLoading(true);
      try {
        const llmFiltersOn = !savedMarkView && Boolean(aiPrecisionMode || minLlmScore);
        const [inventoryPayload, scoredPayload] = await Promise.all([
          fetchJsonWithFallback<{ total?: number }>("/jobs/count"),
          fetchJsonWithFallback<{ total?: number }>(
            "/jobs/count",
            new URLSearchParams({ min_llm_score: "0" }),
          ),
          loadSummary(),
        ]);
        const inventory = Number(inventoryPayload?.total || 0);
        const scored = Number(scoredPayload?.total || 0);
        setInventoryCount(inventory);
        setScoredCount(scored);

        const filteredJobs = await loadJobs(true);
        const shouldRelax =
          llmFiltersOn && filteredJobs.length === 0 && scored === 0 && inventory > 0;
        if (shouldRelax) {
          setFilterRelaxed(true);
          await Promise.all([loadJobs(false), loadCount(false), loadSourceCounts(false)]);
        } else {
          setFilterRelaxed(false);
          await Promise.all([loadCount(true), loadSourceCounts(true)]);
        }
      } finally {
        setListLoading(false);
      }
    };
    void load();
  }, [query, source, minScore, minLlmScore, aiPrecisionMode, limit, locationCategory, markFilter]);

  useEffect(() => {
    void loadOfficialSources();
  }, []);

  const highMatchCount = useMemo(() => jobs.filter((job) => job.match_score >= 80).length, [jobs]);
  const rssBase = useMemo(() => buildPublicBase(), []);
  const allSourcesCount = useMemo(() => {
    if (!sourceCountsLoaded) {
      return null;
    }
    return Object.values(sourceCounts).reduce((sum, value) => sum + Number(value || 0), 0);
  }, [sourceCountsLoaded, sourceCounts]);
  const sourceOptions = useMemo(() => {
    const fromJobs = jobs.map((job) => job.source);
    const fromSummary = summary?.by_source.map((item) => item.source) ?? [];
    const fromCounts = Object.keys(sourceCounts);
    return Array.from(new Set([...fromJobs, ...fromSummary, ...officialSources, ...fromCounts])).sort();
  }, [jobs, summary, officialSources, sourceCounts]);

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
            <option value="">
              {allSourcesCount == null ? "All sources" : `All sources (${allSourcesCount})`}
            </option>
            {sourceOptions.map((item) => {
              const countText = sourceCountsLoaded ? ` (${sourceCounts[item] ?? 0})` : "";
              return (
                <option key={item} value={item}>
                  {`${item}${countText}`}
                </option>
              );
            })}
          </select>
          {officialSourceLoadError ? (
            <p className="field-note warning">
              Official source catalog unavailable, showing only sources present in current jobs.
            </p>
          ) : (
            <p className="field-note">
              Official source catalog loaded
              {officialSourceTotal != null ? ` (${officialSourceTotal} sources)` : ""}.
            </p>
          )}
          {sourceCountsLoadError ? (
            <p className="field-note warning">
              Source counts unavailable for current filters.
            </p>
          ) : sourceCountsLoaded ? (
            <p className="field-note">
              Source counts reflect current filters (AI score, query, location).
            </p>
          ) : null}
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
            <option value="confirmed_yangtze_delta">Confirmed Jiangsu/Zhejiang</option>
            <option value="confirmed_hong_kong">Confirmed Hong Kong</option>
            <option value="confirmed_malaysia">Confirmed Malaysia</option>
            <option value="confirmed_southeast_asia">Confirmed Southeast Asia</option>
            <option value="unclassified">Unclassified</option>
          </select>
        </div>
        <div className="field">
          <label>My Marks</label>
          <select value={markFilter} onChange={(event) => setMarkFilter(event.target.value)}>
            <option value="">All</option>
            <option value="favorited">Favorites</option>
            <option value="applied">Applied</option>
            <option value="not_applied">Not applied</option>
            <option value="not_viewed">Not viewed yet</option>
          </select>
          {savedMarkView && (
            <p className="field-note">Includes closed jobs; AI and rule score filters are ignored.</p>
          )}
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

      {filterRelaxed && (
        <section className="notice glass">
          Worker has collected <strong>{inventoryCount}</strong> jobs, but AI scoring has not
          finished yet ({scoredCount} scored). Showing collected jobs by rule score. AI Precision
          will apply automatically once the LLM rerank writes scores.
        </section>
      )}

      <section className="job-list">
        {listLoading ? (
          <div className="empty glass">Loading collected jobs...</div>
        ) : jobs.length === 0 ? (
          <div className="empty glass">
            {markFilter
              ? "No jobs with this mark yet."
              : inventoryCount > 0
              ? "No jobs matched current filters. Try setting AI Score to All or turning AI Precision Mode Off."
              : "No collected jobs yet. The worker is still running official-source collectors."}
          </div>
        ) : (
          jobs.map((job) => (
            <article
              key={job.id}
              className={`job-card glass${job.last_viewed_at ? " viewed" : ""}${job.applied_at ? " applied" : ""}`}
            >
              <div>
                <p className="job-company">{job.company}</p>
                <h2>{job.title}</h2>
                <p className="job-meta">
                  {job.location} · {job.source}
                </p>
                {job.llm_fit_score != null ? (
                  <p className="job-meta">
                    LLM Fit: {Math.round(job.llm_fit_score)} ({job.llm_verdict || "n/a"})
                  </p>
                ) : (
                  <p className="job-meta">AI score pending</p>
                )}
                <span className="location-badge">
                  {LOCATION_BADGES[job.location_category] ?? "Location unclassified"}
                </span>
                {job.posted_at && <p className="job-meta">Posted: {new Date(job.posted_at).toLocaleString()}</p>}
                {renderMarkBadges(job)}
              </div>
              <div className="job-right">
                <span className="score">
                  {job.llm_fit_score != null ? `AI ${Math.round(job.llm_fit_score)}` : `Rule ${Math.round(job.match_score)}`}
                </span>
                <a
                  className="button small"
                  href={job.apply_url}
                  target="_blank"
                  onClick={() => void recordView(job.id)}
                >
                  Apply Now
                </a>
                <button className="button small detail-btn" onClick={() => void loadJobDetail(job.id)}>
                  View Details
                </button>
                {renderMarkButtons(job)}
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
                    {renderMarkBadges(selectedJob)}
                  </div>
                  <button className="button small detail-close" onClick={() => setSelectedJob(null)}>
                    Close
                  </button>
                </div>
                <div className="detail-actions">
                  <a
                    className="button small primary"
                    href={selectedJob.apply_url}
                    target="_blank"
                    onClick={() => void recordView(selectedJob.id)}
                  >
                    Apply Now
                  </a>
                  <a className="button small" href={selectedJob.source_url} target="_blank">
                    Open Source
                  </a>
                  {renderMarkButtons(selectedJob)}
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
