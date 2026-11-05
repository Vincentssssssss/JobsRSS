# Architecture

## Backend

FastAPI

Responsibilities:

- REST API
- RSS endpoints
- Job queries
- Health checks

---

## Collector

Responsible only for:

- fetching source data
- parsing source data
- returning normalized/raw jobs

Collectors should not:

- calculate matching scores
- send notifications
- directly manipulate unrelated tables

---

## Normalizer

Responsible for:

- title normalization
- company normalization
- location normalization
- description cleanup
- date normalization

---

## Deduplication

Responsible for:

- source-level duplicate detection
- cross-source duplicate detection

---

## Matcher

Responsible for:

- keyword matching
- skill matching
- seniority matching
- location matching

---

## RSS

Responsible for generating feeds from database records.

---

## Scheduler

Responsible for:

- executing collectors
- scheduling
- retry
- logging
- failure isolation
