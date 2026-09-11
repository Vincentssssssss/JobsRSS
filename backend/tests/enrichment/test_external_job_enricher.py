import socket
from unittest.mock import patch

from app.enrichment.external_job import (
    ExternalJobEnricher,
    EnrichedJobData,
    detect_ats_provider,
    merge_job_fields,
)


def test_detects_common_ats_providers():
    assert detect_ats_provider("https://acme.wd5.myworkdayjobs.com/en-US/jobs/job/123") == "workday"
    assert detect_ats_provider("https://boards.greenhouse.io/acme/jobs/123") == "greenhouse"
    assert detect_ats_provider("https://jobs.lever.co/acme/abc") == "lever"
    assert detect_ats_provider("https://jobs.smartrecruiters.com/Acme/123") == "smartrecruiters"
    assert detect_ats_provider("https://jobs.acme.com/security/123") == "company_site"
    assert detect_ats_provider("https://lever.co.attacker.example/acme/123") == "company_site"


def test_extracts_jobposting_json_ld():
    html = """
    <html><head>
      <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Principal Cloud Security Architect",
        "description": "<p>Own multi-cloud security architecture and IAM.</p>",
        "datePosted": "2026-08-20",
        "hiringOrganization": {"@type": "Organization", "name": "Acme Cloud"},
        "jobLocation": {
          "@type": "Place",
          "address": {
            "@type": "PostalAddress",
            "addressLocality": "Shanghai",
            "addressCountry": "CN"
          }
        }
      }
      </script>
    </head></html>
    """

    result = ExternalJobEnricher.parse_html(
        html,
        final_url="https://jobs.acme.com/123",
        provider="company_site",
    )

    assert result.company == "Acme Cloud"
    assert result.title == "Principal Cloud Security Architect"
    assert result.location == "Shanghai, CN"
    assert result.description == "Own multi-cloud security architecture and IAM."
    assert result.posted_at.isoformat().startswith("2026-08-20")


def test_merge_prefers_official_fields_but_preserves_linkedin_source():
    linkedin = {
        "title": "Cloud Security Architect",
        "company": "Unknown Company",
        "location": "Shanghai",
        "description": "Cloud Security Architect at Unknown Company in Shanghai",
        "job_url": "https://www.linkedin.com/jobs/view/123/",
        "posted_at": None,
    }
    official = EnrichedJobData(
        official_url="https://jobs.acme.com/123",
        provider="workday",
        title="Principal Cloud Security Architect",
        company="Acme Cloud",
        location="Shanghai, CN",
        description=(
            "Own cloud security architecture, IAM, DevSecOps, and multi-cloud controls "
            "across the regional platform."
        ),
        posted_at=None,
    )

    merged = merge_job_fields(linkedin, official)

    assert merged["company"] == "Acme Cloud"
    assert merged["description"].startswith("Own cloud security architecture")
    assert merged["apply_url"] == "https://jobs.acme.com/123"
    assert merged["source_url"] == "https://www.linkedin.com/jobs/view/123/"


def test_rejects_non_public_enrichment_urls():
    assert not ExternalJobEnricher.is_safe_public_url("http://localhost:8000/private")
    assert not ExternalJobEnricher.is_safe_public_url("http://postgres:5432/private")
    assert not ExternalJobEnricher.is_safe_public_url("http://foo.localhost/private")
    assert not ExternalJobEnricher.is_safe_public_url("http://127.0.0.1/admin")
    assert not ExternalJobEnricher.is_safe_public_url("https://user@jobs.lever.co/acme/123")
    assert not ExternalJobEnricher.is_safe_public_url("file:///etc/passwd")
    assert ExternalJobEnricher.is_safe_public_url("https://jobs.acme.com/123")
    assert ExternalJobEnricher.is_supported_ats_url("https://jobs.lever.co/acme/123")
    assert not ExternalJobEnricher.is_supported_ats_url("https://jobs.acme.com/123")


def test_rejects_hostname_that_resolves_to_private_address():
    private_result = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.4", 443))]
    public_result = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]

    with patch("app.enrichment.external_job.socket.getaddrinfo", return_value=private_result):
        assert not ExternalJobEnricher.is_safe_public_url("https://jobs.acme.com/123", resolve_dns=True)
    with patch("app.enrichment.external_job.socket.getaddrinfo", return_value=public_result):
        assert ExternalJobEnricher.is_safe_public_url("https://jobs.acme.com/123", resolve_dns=True)
