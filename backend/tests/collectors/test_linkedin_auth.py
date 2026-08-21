from app.collectors.linkedin_auth import LinkedInAuthCollector


def test_canonicalizes_linkedin_job_url_and_removes_tracking():
    collector = LinkedInAuthCollector()

    result = collector._clean_linkedin_job_url(
        "https://sg.linkedin.com/jobs/view/cloud-security-at-acme-4451905595"
        "?position=32&trackingId=secret"
    )

    assert result == "https://sg.linkedin.com/jobs/view/4451905595/"


def test_extracts_company_from_linkedin_job_slug():
    collector = LinkedInAuthCollector()

    company = collector._company_from_job_url(
        "https://sg.linkedin.com/jobs/view/devsecops-engineer-at-assurity-trusted-solutions-pte-ltd-4451337319/"
    )

    assert company == "Assurity Trusted Solutions Pte Ltd"


def test_does_not_treat_search_urls_as_jobs():
    collector = LinkedInAuthCollector()

    assert collector.is_job_url("https://www.linkedin.com/jobs/view/4451337319/")
    assert not collector.is_job_url("https://www.linkedin.com/jobs/search/?keywords=security")


def test_extracts_title_from_linkedin_job_slug():
    collector = LinkedInAuthCollector()

    title = collector._title_from_job_url(
        "https://sg.linkedin.com/jobs/view/devsecops-engineer-iam-at-acme-4451337319/"
    )

    assert title == "DevSecOps Engineer IAM"
