from app.official.collectors.roche import parse_roche_job
from app.official.location import LocationCategory


def test_parses_roche_phenom_detail_job():
    listing = {
        "jobId": "202608-120483",
        "jobSeqNo": "ROCHGLOBAL202608120483EXTERNALENGLOBAL",
        "title": "Security Transformation Lead",
        "location": "Shanghai, Shanghai, China's Mainland",
        "postedDate": "2026-08-20T00:00:00.000+0000",
        "applyUrl": "https://roche.wd3.myworkdayjobs.com/roche-ext/job/Shanghai/job/apply",
    }
    detail = {
        "jobDetail": {
            "data": {
                "job": {
                    "companyName": "Roche",
                    "structureData": {
                        "@type": "JobPosting",
                        "title": "Security Transformation Lead",
                        "description": (
                            "<p>Lead cloud security, IAM, and application security "
                            "transformation across China.</p>"
                        ),
                        "datePosted": "2026-08-20",
                        "jobLocation": {
                            "address": {
                                "addressLocality": "Shanghai",
                                "addressRegion": "Shanghai",
                                "addressCountry": "China's Mainland",
                            }
                        },
                    },
                }
            }
        }
    }

    job = parse_roche_job(listing, detail)

    assert job["source_job_id"] == listing["jobSeqNo"]
    assert job["company"] == "Roche"
    assert job["location_category"] == LocationCategory.CONFIRMED_SHANGHAI.value
    assert "IAM" in job["description"]
