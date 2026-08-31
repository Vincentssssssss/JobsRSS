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


def test_strict_location_filter_accepts_only_configured_markets():
    collector = LinkedInAuthCollector()
    allowed = ["Singapore", "Hong Kong", "Shanghai", "Jiangsu", "Zhejiang"]

    assert collector._is_allowed_location("Singapore", allowed)
    assert collector._is_allowed_location("新加坡", allowed)
    assert collector._is_allowed_location("Hong Kong SAR", allowed)
    assert collector._is_allowed_location("香港特别行政区", allowed)
    assert collector._is_allowed_location("上海市", allowed)
    assert collector._is_allowed_location("Hangzhou, Zhejiang, China", allowed)
    assert collector._is_allowed_location("杭州市", allowed)
    assert collector._is_allowed_location("Nanjing, Jiangsu, China", allowed)
    assert collector._is_allowed_location("苏州, 江苏省, 中国", allowed)
    assert collector._is_allowed_location("Ningbo, Zhejiang, China", allowed)

    assert not collector._is_allowed_location("Beijing", allowed)
    assert not collector._is_allowed_location("Shenzhen", allowed)
    assert not collector._is_allowed_location("Remote - APAC", allowed)
    assert not collector._is_allowed_location("Unknown", allowed)


def test_strict_location_filter_supports_jiangzhehu_group_keyword():
    collector = LinkedInAuthCollector()
    allowed = ["江浙沪"]

    assert collector._is_allowed_location("上海", allowed)
    assert collector._is_allowed_location("苏州, 江苏, 中国", allowed)
    assert collector._is_allowed_location("杭州, 浙江, 中国", allowed)
    assert not collector._is_allowed_location("Beijing", allowed)


def test_strict_filter_rejects_search_url_fallback_location():
    collector = LinkedInAuthCollector()
    allowed = ["Shanghai"]
    merged = {
        "location": "Shanghai",
        "location_source": "fallback",
    }

    assert not collector._passes_strict_location_filter(merged, allowed)


def test_merge_prefers_explicit_detail_location_over_search_fallback():
    collector = LinkedInAuthCollector()
    card = {
        "title": "IAM Lead",
        "company": "ICF",
        "location": "",
        "job_url": "https://www.linkedin.com/jobs/view/123456789/",
        "posted_at": None,
    }
    detail = {
        "title": "IAM Lead",
        "company": "ICF",
        "location": "Richmond, VA",
        "description": "IAM leadership role.",
        "external_apply_url": "",
        "official": None,
    }

    merged = collector._merge_job_data(card, detail, fallback_location="Shanghai")

    assert merged["location"] == "Richmond"
    assert merged["location_source"] == "detail"


def test_clean_description_prefers_role_content_over_company_intro():
    collector = LinkedInAuthCollector()
    raw = """
The Hong Kong Jockey Club Founded in 1884, The Hong Kong Jockey Club is a world-class racing club.
Who are we? We are the IT Division with global teams.
What do we do? We design and operate technology.
Responsibilities:
- Lead platform and network security controls.
- Drive cloud security architecture and vulnerability governance.
Requirements:
- 8+ years in cybersecurity, network security, or cloud security.
"""

    cleaned = collector._clean_description(raw)

    assert "Founded in 1884" not in cleaned
    assert "Who are we?" not in cleaned
    assert "Lead platform and network security controls." in cleaned
    assert "8+ years in cybersecurity" in cleaned


def test_clean_description_drops_noise_lines_without_emptying_payload():
    collector = LinkedInAuthCollector()
    raw = """
Responsibilities: Build and tune SIEM detection pipelines.
Read our privacy policy for more information.
Requirements: Hands-on SOC and threat detection experience.
"""

    cleaned = collector._clean_description(raw)

    assert "privacy policy" not in cleaned.lower()
    assert "Build and tune SIEM detection pipelines." in cleaned
    assert "Hands-on SOC and threat detection experience." in cleaned
