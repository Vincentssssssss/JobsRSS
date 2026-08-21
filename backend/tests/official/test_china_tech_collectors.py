from app.official.collectors.feishu_jobs import parse_feishu_jobs
from app.official.collectors.huawei import parse_huawei_jobs
from app.official.collectors.tencent import parse_tencent_jobs
from app.official.location import LocationCategory


def test_parses_tencent_shanghai_jobs():
    payload = {
        "Data": {
            "Posts": [
                {
                    "PostId": "123",
                    "RecruitPostName": "腾讯云安全架构师",
                    "LocationName": "上海",
                    "BGName": "CSIG",
                    "ProductName": "腾讯云",
                    "Responsibility": "负责腾讯云安全架构。",
                    "Requirement": "具备 IAM 与 DevSecOps 经验。",
                    "LastUpdateTime": "2026-08-20",
                }
            ]
        }
    }

    jobs = parse_tencent_jobs(payload)

    assert len(jobs) == 1
    assert jobs[0]["source_job_id"] == "123"
    assert jobs[0]["location_category"] == LocationCategory.CONFIRMED_SHANGHAI.value
    assert "DevSecOps" in jobs[0]["description"]


def test_parses_huawei_gateway_jobs():
    payload = {
        "result": {
            "data": [
                {
                    "advertisementId": "HW-100",
                    "jobName": "云安全架构师",
                    "jobAddress": "China\\Shanghai-Shanghai",
                    "jobResponsibility": "负责云安全架构。",
                    "jobRequirement": "具备安全架构和 IAM 经验。",
                    "lastUpdateDate": "2026-08-20",
                }
            ]
        }
    }

    jobs = parse_huawei_jobs(payload)

    assert len(jobs) == 1
    assert jobs[0]["source_job_id"] == "HW-100"
    assert jobs[0]["location_category"] == LocationCategory.CONFIRMED_SHANGHAI.value


def test_parses_shared_feishu_recruiting_payload():
    payload = {
        "data": {
            "job_post_list": [
                {
                    "id": "BD-200",
                    "title": "Cloud Security Engineer",
                    "description": "Build cloud security controls.",
                    "requirement": "IAM and application security.",
                    "location_list": [{"name": "上海"}],
                    "publish_time": 1787184000,
                }
            ]
        }
    }

    jobs = parse_feishu_jobs(
        payload,
        company="ByteDance",
        source_root="https://jobs.bytedance.com",
        detail_path="/experienced/position/{id}/detail",
    )

    assert len(jobs) == 1
    assert jobs[0]["source_job_id"] == "BD-200"
    assert jobs[0]["location_category"] == LocationCategory.CONFIRMED_SHANGHAI.value
    assert jobs[0]["source_url"].endswith("/experienced/position/BD-200/detail")
