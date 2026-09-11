# Requirements

## Functional Requirements

### FR-001 Job Collection

The system shall periodically collect jobs from configured sources.

### FR-002 Job Normalization

All collected jobs shall be converted into a common schema.

### FR-003 Deduplication

The system shall detect duplicate jobs across sources.

### FR-004 Job Matching

The system shall calculate a relevance score from 0 to 100.

### FR-005 RSS

The system shall expose RSS feeds.

### FR-006 Application

Every job should expose the best available application URL.

### FR-007 Scheduling

Collectors shall run automatically.

### FR-008 Failure Isolation

A failed collector shall not stop other collectors.

---

# Non-Functional Requirements

## Reliability

The service should run continuously.

## Maintainability

New job sources should be added without modifying core business logic.

## Observability

Every collector should produce:

- start time
- end time
- number of jobs found
- number of new jobs
- number of duplicates
- number of errors

## Security

Secrets must be stored in environment variables.

No credentials may be committed to Git.

## Deployment

The system must be deployable using Docker Compose.
