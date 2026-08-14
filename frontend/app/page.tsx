"use client";

import { useEffect, useMemo, useState } from "react";

type JobCard = {
  id: number;
  company: string;
  title: string;
  location: string;
  match_score: number;
  apply_url: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export default function HomePage() {
  const [jobs, setJobs] = useState<JobCard[]>([]);

  useEffect(() => {
    const load = async () => {
      try {
        const response = await fetch(`${API_BASE}/jobs?limit=20`, { cache: "no-store" });
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
    void load();
  }, []);

  const highMatchCount = useMemo(() => jobs.filter((job) => job.match_score >= 80).length, [jobs]);

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
      </section>

      <section className="job-list">
        {jobs.length === 0 ? (
          <div className="empty glass">No jobs available yet. Start collectors from the worker service.</div>
        ) : (
          jobs.map((job) => (
            <article key={job.id} className="job-card glass">
              <div>
                <p className="job-company">{job.company}</p>
                <h2>{job.title}</h2>
                <p className="job-meta">{job.location}</p>
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
