"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import packageJson from "../package.json";

// Baked in at `next build`, so a dashboard image older than the checked-out code shows an older version.
const DASHBOARD_VERSION = packageJson.version;

type JobCard = {
  id: number;
  company: string;
  title: string;
  location: string;
  match_score: number;
  apply_url: string;
  source: string;
  posted_at?: string | null;
  first_seen_at?: string | null;
  location_category: string;
  llm_fit_score?: number | null;
  llm_verdict?: string | null;
  llm_role_family?: string | null;
  status?: string;
  favorited_at?: string | null;
  applied_at?: string | null;
  last_viewed_at?: string | null;
  view_count?: number;
  country?: string | null;
  cities?: string[];
  location_label?: string;
};

type MarkUpdate = { favorited?: boolean; applied?: boolean };

type DescriptionSection = {
  title: string;
  lines: string[];
};

type JobDetail = JobCard & {
  description: string;
  updated_at?: string | null;
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

type LocationsResponse = {
  total: number;
  unknown: number;
  countries: Array<{
    country: string;
    label: string;
    count: number;
    cities: Array<{ city: string; label: string; count: number }>;
  }>;
};

const LOCATION_BADGES: Record<string, string> = {
  confirmed_shanghai: "Shanghai",
  confirmed_yangtze_delta: "Jiangsu/Zhejiang",
  confirmed_hong_kong: "Hong Kong",
  confirmed_malaysia: "Malaysia",
  confirmed_southeast_asia: "Southeast Asia",
  excluded: "Outside target areas",
};

// The location picker's value: "city:<standard name>" or "country:<standard name>".
function placeParams(place: string): [string, string] | null {
  const separator = place.indexOf(":");
  if (separator <= 0) {
    return null;
  }
  return [place.slice(0, separator), place.slice(separator + 1)];
}

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

function formatShortDate(value: string): string {
  return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function formatLongDate(value: string): string {
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function formatAge(value: string): string {
  const days = Math.floor((Date.now() - new Date(value).getTime()) / 86_400_000);
  if (days <= 0) {
    return "today";
  }
  if (days < 30) {
    return `${days}d ago`;
  }
  const months = Math.floor(days / 30);
  return months < 12 ? `${months}mo ago` : `${Math.floor(days / 365)}y ago`;
}

// These portals only expose when a posting was last updated, not when it was published.
const UPDATE_DATE_SOURCES = new Set(["official_tencent", "official_huawei"]);

type JobDate = { kind: "Posted" | "Updated" | "First seen"; value: string; note: string };

function jobDate(job: JobCard): JobDate | null {
  if (job.posted_at) {
    const kind = UPDATE_DATE_SOURCES.has(job.source) ? "Updated" : "Posted";
    const note =
      kind === "Updated" ? "This source only shows when the posting was last updated." : "";
    return { kind, value: job.posted_at, note };
  }
  if (job.first_seen_at) {
    return {
      kind: "First seen",
      value: job.first_seen_at,
      note: "This source gives no posting date; this is when JobsRSS first collected it.",
    };
  }
  return null;
}

const SORT_STORAGE_KEY = "jobsrss.sort";
const SORT_OPTIONS = ["newest", "ai_score"];

function shortSource(source: string): string {
  return source.replace(/^official_/, "");
}

function scoreTone(job: JobCard): string {
  if (job.llm_fit_score == null) {
    return "pending";
  }
  if (job.llm_verdict === "strong_fit") {
    return "strong";
  }
  return job.llm_verdict === "possible_fit" ? "possible" : "weak";
}

// The region badge is noise when the standardized place already names it ("香港 Hong Kong").
function regionBadge(job: JobCard): string | null {
  const label = LOCATION_BADGES[job.location_category];
  if (!label) {
    return null;
  }
  const place = job.location_label || job.location || "";
  return place.includes(label) ? null : label;
}

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  return target.isContentEditable || ["INPUT", "SELECT", "TEXTAREA"].includes(target.tagName);
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
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [source, setSource] = useState("");
  const [minScore, setMinScore] = useState(0);
  const [minLlmScore, setMinLlmScore] = useState("60");
  const [aiPrecisionMode, setAiPrecisionMode] = useState(true);
  const [limit, setLimit] = useState(500);
  const [locationCategory, setLocationCategory] = useState("");
  const [place, setPlace] = useState("");
  const [locations, setLocations] = useState<LocationsResponse | null>(null);
  const [markFilter, setMarkFilter] = useState("");
  // null until the saved choice is read, so the first list request already uses it.
  const [sortBy, setSortBy] = useState<string | null>(null);
  const [pendingMarks, setPendingMarks] = useState<Record<number, boolean>>({});
  const [selectedJob, setSelectedJob] = useState<JobDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [openJobId, setOpenJobId] = useState<number | null>(null);
  const [apiVersion, setApiVersion] = useState<string | null>(null);
  const detailRequest = useRef(0);
  const lastOpenedJobId = useRef<number | null>(null);
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
    if (debouncedQuery.trim()) {
      params.set("q", debouncedQuery.trim());
    }
    if (source) {
      params.set("source", source);
    }
    if (locationCategory) {
      params.set("location_category", locationCategory);
    }
    const placeFilter = placeParams(place);
    if (placeFilter) {
      params.set(placeFilter[0], placeFilter[1]);
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

  // Loaders take isCurrent so a slow response for an older filter state (an
  // earlier keystroke, say) cannot overwrite the results of the latest one.
  const loadJobs = async (includeLlm: boolean, isCurrent: () => boolean) => {
    let payload: JobCard[] | null = null;
    const params = buildJobParams(includeLlm, true);
    params.set("sort", sortBy ?? "newest");
    try {
      payload = await fetchJsonWithFallback<JobCard[]>("/jobs", params);
    } catch {
      payload = null;
    }
    if (isCurrent()) {
      setJobs(payload ?? []);
    }
    return payload ?? [];
  };

  const loadSummary = async (isCurrent: () => boolean) => {
    let payload: SummaryResponse | null = null;
    try {
      payload = await fetchJsonWithFallback<SummaryResponse>("/jobs/summary/last-24h");
    } catch {
      payload = null;
    }
    if (isCurrent()) {
      setSummary(payload);
    }
  };

  const loadCount = async (includeLlm: boolean, isCurrent: () => boolean) => {
    let total = 0;
    try {
      const payload = await fetchJsonWithFallback<{ total?: number }>(
        "/jobs/count",
        buildJobParams(includeLlm, false),
      );
      total = Number(payload?.total || 0);
    } catch {
      total = 0;
    }
    if (isCurrent()) {
      setTotalCount(total);
    }
    return total;
  };

  const loadSourceCounts = async (includeLlm: boolean, isCurrent: () => boolean) => {
    const params = buildJobParams(includeLlm, false);
    params.delete("source");
    try {
      const payload = await fetchJsonWithFallback<SourceCountsResponse>("/jobs/source-counts", params);
      if (!isCurrent()) {
        return;
      }
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
      if (!isCurrent()) {
        return;
      }
      setSourceCounts({});
      setSourceCountsLoaded(false);
      setSourceCountsLoadError(true);
    }
  };

  const loadLocations = async (includeLlm: boolean, isCurrent: () => boolean) => {
    const params = buildJobParams(includeLlm, false);
    params.delete("city");
    params.delete("country");
    let payload: LocationsResponse | null = null;
    try {
      payload = await fetchJsonWithFallback<LocationsResponse>("/jobs/locations", params);
    } catch {
      payload = null;
    }
    if (isCurrent()) {
      setLocations(payload);
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

  const renderMarkButtons = (job: JobCard, size: "small" | "tiny" = "small") => (
    <>
      <button
        className={`button ${size} mark-btn${job.favorited_at ? " active-favorite" : ""}`}
        disabled={Boolean(pendingMarks[job.id])}
        onClick={() => void toggleMark(job, { favorited: !job.favorited_at })}
        title={job.favorited_at ? `Favorited ${formatShortTime(job.favorited_at)}` : "Save to favorites"}
      >
        {job.favorited_at ? "★ Favorited" : "☆ Favorite"}
      </button>
      <button
        className={`button ${size} mark-btn${job.applied_at ? " active-applied" : ""}`}
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

  const openJob = async (jobId: number) => {
    const request = ++detailRequest.current;
    lastOpenedJobId.current = jobId;
    setOpenJobId(jobId);
    setDetailLoading(true);
    const viewed = sendJsonWithFallback<JobCard>("POST", `/jobs/${jobId}/view`);
    let payload: JobDetail | null = null;
    try {
      payload = await fetchJsonWithFallback<JobDetail>(`/jobs/${jobId}`);
    } catch {
      payload = null;
    }
    // Stepping through jobs quickly can finish requests out of order; only the latest may fill the panel.
    if (request === detailRequest.current) {
      setSelectedJob(payload);
      setDetailLoading(false);
    }
    // Applied after the detail is set so the panel shows this view even if the GET raced ahead of it.
    const updated = await viewed;
    if (updated) {
      applyJobUpdate(updated);
    }
  };

  const closeJob = () => {
    detailRequest.current += 1;
    setOpenJobId(null);
    setSelectedJob(null);
    setDetailLoading(false);
  };

  // The list reflows between the full-width and split layouts, so keep the job being
  // read (or just closed) on screen instead of leaving the reader somewhere else.
  useEffect(() => {
    const targetId = openJobId ?? lastOpenedJobId.current;
    if (targetId == null) {
      return;
    }
    const frame = window.requestAnimationFrame(() => {
      document
        .getElementById(`job-${targetId}`)
        ?.scrollIntoView({ block: openJobId == null ? "center" : "nearest" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [openJobId]);

  useEffect(() => {
    if (openJobId == null) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey || isTypingTarget(event.target)) {
        return;
      }
      if (event.key === "Escape") {
        closeJob();
        return;
      }
      const step = event.key === "j" ? 1 : event.key === "k" ? -1 : 0;
      if (!step) {
        return;
      }
      const index = jobs.findIndex((job) => job.id === openJobId);
      const next = jobs[index + step];
      if (index >= 0 && next) {
        event.preventDefault();
        void openJob(next.id);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [openJobId, jobs]);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(query), 300);
    return () => window.clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    let saved: string | null = null;
    try {
      saved = window.localStorage.getItem(SORT_STORAGE_KEY);
    } catch {
      saved = null;
    }
    setSortBy(saved && SORT_OPTIONS.includes(saved) ? saved : "newest");
  }, []);

  const changeSort = (value: string) => {
    setSortBy(value);
    try {
      window.localStorage.setItem(SORT_STORAGE_KEY, value);
    } catch {
      // Private browsing can refuse storage; the choice then lasts until reload.
    }
  };

  useEffect(() => {
    if (sortBy === null) {
      return;
    }
    let current = true;
    const isCurrent = () => current;
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
          loadSummary(isCurrent),
        ]);
        if (!isCurrent()) {
          return;
        }
        const inventory = Number(inventoryPayload?.total || 0);
        const scored = Number(scoredPayload?.total || 0);
        setInventoryCount(inventory);
        setScoredCount(scored);

        const filteredJobs = await loadJobs(true, isCurrent);
        if (!isCurrent()) {
          return;
        }
        const shouldRelax =
          llmFiltersOn && filteredJobs.length === 0 && scored === 0 && inventory > 0;
        if (shouldRelax) {
          setFilterRelaxed(true);
          await Promise.all([
            loadJobs(false, isCurrent),
            loadCount(false, isCurrent),
            loadSourceCounts(false, isCurrent),
            loadLocations(false, isCurrent),
          ]);
        } else {
          setFilterRelaxed(false);
          await Promise.all([
            loadCount(true, isCurrent),
            loadSourceCounts(true, isCurrent),
            loadLocations(true, isCurrent),
          ]);
        }
      } finally {
        if (isCurrent()) {
          setListLoading(false);
        }
      }
    };
    void load();
    return () => {
      current = false;
    };
  }, [debouncedQuery, source, minScore, minLlmScore, aiPrecisionMode, limit, locationCategory, place, markFilter, sortBy]);

  useEffect(() => {
    void loadOfficialSources();
    void fetchJsonWithFallback<{ version?: string }>("/healthz").then((payload) => {
      setApiVersion(payload?.version ?? null);
    });
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
        <h1>
          JobsRSS Intelligence{" "}
          <span className="version-tag" data-app-version={DASHBOARD_VERSION}>
            v{DASHBOARD_VERSION}
          </span>
        </h1>
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
            placeholder="cloud security / 架构师 / 上海 / Hong Kong"
          />
          <p className="field-note">
            Place names in Chinese or English (上海, Hangzhou, 香港, KL, 新加坡) also match the
            standardized location, whatever format the source uses.
          </p>
        </div>
        <div className="field">
          <label>Location</label>
          <select value={place} onChange={(event) => setPlace(event.target.value)}>
            <option value="">
              {locations ? `All locations (${locations.total})` : "All locations"}
            </option>
            {placeParams(place) &&
              !locations?.countries.some(
                (item) =>
                  place === `country:${item.country}` ||
                  item.cities.some((city) => place === `city:${city.city}`),
              ) && <option value={place}>{`${placeParams(place)?.[1]} (0)`}</option>}
            {locations?.countries.map((item) => (
              <optgroup key={item.country} label={`${item.label} (${item.count})`}>
                {!(item.cities.length === 1 && item.cities[0].city === item.country) && (
                  <option value={`country:${item.country}`}>{`All of ${item.label} (${item.count})`}</option>
                )}
                {item.cities.map((city) => (
                  <option key={city.city} value={`city:${city.city}`}>
                    {`${city.label} (${city.count})`}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
          {locations && locations.unknown > 0 && (
            <p className="field-note">{locations.unknown} jobs list no recognizable place.</p>
          )}
        </div>
        <div className="field">
          <label>Sort By</label>
          <select value={sortBy ?? "newest"} onChange={(event) => changeSort(event.target.value)}>
            <option value="newest">Newest posted first</option>
            <option value="ai_score">AI score, highest first</option>
          </select>
          <p className="field-note">
            {sortBy === "ai_score"
              ? "Jobs without an AI score come last, by rule score."
              : "Jobs without a posting date sort by when they were first collected."}
          </p>
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
          <label>Target Region</label>
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
            <option value="excluded">Outside target areas</option>
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

      {apiVersion && apiVersion !== DASHBOARD_VERSION && (
        <section className="notice glass warning">
          This dashboard is <strong>v{DASHBOARD_VERSION}</strong> but the API is{" "}
          <strong>v{apiVersion}</strong>, so the dashboard container still runs older code. Run{" "}
          <code>docker compose up -d --force-recreate --no-build frontend</code>, wait about a
          minute and reload the page.
        </section>
      )}

      {filterRelaxed && (
        <section className="notice glass">
          Worker has collected <strong>{inventoryCount}</strong> jobs, but AI scoring has not
          finished yet ({scoredCount} scored). Showing collected jobs by rule score. AI Precision
          will apply automatically once the LLM rerank writes scores.
        </section>
      )}

      <div className={`workspace${openJobId != null ? " split" : ""}`}>
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
            jobs.map((job) => {
              const region = regionBadge(job);
              const date = jobDate(job);
              const closed = job.status != null && job.status !== "active";
              return (
                <article
                  key={job.id}
                  id={`job-${job.id}`}
                  className={`job-card glass${job.last_viewed_at ? " viewed" : ""}${job.applied_at ? " applied" : ""}${job.id === openJobId ? " open" : ""}`}
                >
                  <div className="job-head" onClick={() => void openJob(job.id)}>
                    <div className="job-text">
                      <h2>
                        <button type="button" className="job-title" title={job.title}>
                          {job.favorited_at && (
                            <span className="fav-star" title="Favorited">
                              ★{" "}
                            </span>
                          )}
                          {job.title}
                        </button>
                      </h2>
                      <p className="job-line" title={job.location}>
                        <span className="job-line-company">{job.company}</span>
                        <span>{job.location_label || job.location}</span>
                        <span>{shortSource(job.source)}</span>
                      </p>
                    </div>
                    <div className="job-side">
                      <span className={`score ${scoreTone(job)}`} title={job.llm_verdict || "AI score pending"}>
                        {job.llm_fit_score != null
                          ? `AI ${Math.round(job.llm_fit_score)}`
                          : `Rule ${Math.round(job.match_score)}`}
                      </span>
                      {date && (
                        <span
                          className={`job-date${date.kind === "Posted" ? "" : " estimated"}`}
                          title={`${date.kind} ${formatLongDate(date.value)}${date.note ? `. ${date.note}` : ""}`}
                        >
                          {date.kind} {formatShortDate(date.value)} · {formatAge(date.value)}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="job-footer">
                    {region && <span className="location-badge">{region}</span>}
                    {job.applied_at && (
                      <span className="mark-badge applied">Applied {formatShortTime(job.applied_at)}</span>
                    )}
                    {job.last_viewed_at && (
                      <span className="mark-badge viewed">
                        Viewed {job.view_count ?? 0}× · last {formatShortTime(job.last_viewed_at)}
                      </span>
                    )}
                    {closed && <span className="mark-badge closed">Closed</span>}
                    <span className="job-footer-spacer" />
                    <a
                      className="button tiny primary"
                      href={job.apply_url}
                      target="_blank"
                      onClick={() => void recordView(job.id)}
                    >
                      Apply Now
                    </a>
                    <button className="button tiny" onClick={() => void openJob(job.id)}>
                      Details
                    </button>
                    {renderMarkButtons(job, "tiny")}
                  </div>
                </article>
              );
            })
          )}
        </section>

        {openJobId != null && (
          <>
            <div className="detail-backdrop" onClick={closeJob} />
            <aside className="detail-pane glass" aria-label="Job details">
              {(() => {
                const detail = selectedJob && selectedJob.id === openJobId ? selectedJob : null;
                const card = detail ?? jobs.find((job) => job.id === openJobId) ?? null;
                if (!card) {
                  return <p className="detail-loading">Loading full job details...</p>;
                }
                return (
                  <>
                    <div className="detail-header">
                      <div>
                        <p className="job-company">{card.company}</p>
                        <h2>{card.title}</h2>
                        <p className="job-meta">
                          {card.location_label || card.location} · {card.source}
                        </p>
                        {(() => {
                          const date = jobDate(card);
                          return date ? (
                            <p className="job-meta" title={date.note || undefined}>
                              {date.kind} {formatLongDate(date.value)} ({formatAge(date.value)})
                              {date.note && <span className="job-meta-note"> · {date.note}</span>}
                            </p>
                          ) : (
                            <p className="job-meta">No posting date</p>
                          );
                        })()}
                        {card.location_label && card.location_label !== card.location && (
                          <p className="job-meta">Listed as: {card.location}</p>
                        )}
                        {renderMarkBadges(card)}
                      </div>
                      <div className="detail-header-side">
                        <span className={`score ${scoreTone(card)}`} title={card.llm_verdict || "AI score pending"}>
                          {card.llm_fit_score != null
                            ? `AI ${Math.round(card.llm_fit_score)}`
                            : `Rule ${Math.round(card.match_score)}`}
                        </span>
                        <button className="button small detail-close" onClick={closeJob} title="Close (Esc)">
                          Close
                        </button>
                      </div>
                    </div>
                    <div className="detail-actions">
                      <a
                        className="button small primary"
                        href={card.apply_url}
                        target="_blank"
                        onClick={() => void recordView(card.id)}
                      >
                        Apply Now
                      </a>
                      {detail && (
                        <a className="button small" href={detail.source_url} target="_blank">
                          Open Source
                        </a>
                      )}
                      {renderMarkButtons(card)}
                    </div>
                    <p className="detail-hint">J / K: next / previous job · Esc: close</p>
                    {!detail ? (
                      <p className="detail-loading">{detailLoading ? "Loading full job details..." : "Could not load this job's details."}</p>
                    ) : (
                      <>
                        {detail.llm_match_reasons && (
                          <div className="detail-description">
                            <h3>LLM Match Reasons</h3>
                            <p>{detail.llm_match_reasons}</p>
                          </div>
                        )}
                        {detail.llm_reject_reasons && (
                          <div className="detail-description">
                            <h3>LLM Reject Reasons</h3>
                            <p>{detail.llm_reject_reasons}</p>
                          </div>
                        )}
                        <div className="detail-description">
                          <h3>Description</h3>
                          {detail.description_sections && detail.description_sections.length > 0 ? (
                            <div className="description-sections">
                              {detail.description_sections.map((section, index) => (
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
                            <p>{detail.description || "No description available."}</p>
                          )}
                        </div>
                      </>
                    )}
                  </>
                );
              })()}
            </aside>
          </>
        )}
      </div>
    </main>
  );
}
