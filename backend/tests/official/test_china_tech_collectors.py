from app.official.collectors.alibaba import parse_alibaba_position
from app.official.collectors.feishu_jobs import parse_feishu_jobs
from app.official.collectors.huawei import parse_huawei_jobs
from app.official.collectors.midea import parse_midea_position
from app.official.collectors.moka import parse_moka_job
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


def test_parses_alibaba_campus_position_detail():
    detail = {
        "content": {
            "id": 199903220038,
            "name": "阿里云安全工程师",
            "description": "负责云平台安全架构。",
            "requirement": "熟悉 IAM、DevSecOps 与应用安全。",
            "workLocations": ["上海"],
            "categoryName": "技术",
            "batchName": "校园招聘",
            "graduationDates": "2026-11-01 - 2027-10-31",
            "hiringProgram": "Alibaba 2027 Graduate Recruitment",
        }
    }

    job = parse_alibaba_position(detail)

    assert job["source_job_id"] == "199903220038"
    assert job["location_category"] == LocationCategory.CONFIRMED_SHANGHAI.value
    assert "DevSecOps" in job["description"]
    assert "Batch Name: 校园招聘" in job["description"]
    assert "Graduation Dates: 2026-11-01 - 2027-10-31" in job["description"]


def test_parses_midea_position_detail():
    list_item = {
        "positionId": "8a5ec0d09f0cd643019f35e6957d6b8c",
        "publicationName": "云安全架构师",
        "workingPlace": "上海-闵行",
        "postDuties": "负责云平台安全架构设计。",
        "qualification": "具备 IAM 与应用安全经验。",
        "releaseStartDate": 1788332142000,
    }
    detail_item = {
        "positionId": "8a5ec0d09f0cd643019f35e6957d6b8c",
        "publicationName": "云安全架构师",
        "workingPlace": "上海-闵行",
        "postDuties": "负责云平台安全架构设计。",
        "qualification": "具备 IAM 与应用安全经验。",
        "publicDate": 1788332142000,
    }

    job = parse_midea_position(list_item, detail_item)

    assert job["source_job_id"] == "8a5ec0d09f0cd643019f35e6957d6b8c"
    assert job["location_category"] == LocationCategory.CONFIRMED_SHANGHAI.value
    assert "IAM" in job["description"]
    assert job["source_url"].startswith("https://recruit.midea.com/recruit-out/#/position")


def test_parses_anta_moka_detail_payload():
    detail_item = {
        "id": "e105f85c-012a-43bb-9ca0-c48bc2a6a639",
        "title": "CRM会员运营主管",
        "jobDescription": "<p>岗位职责：负责会员数据治理。</p><p>任职要求：5年经验。</p>",
        "locations": [
            {
                "country": "中国",
                "address": "上海市闵行区中骏广场",
            }
        ],
        "publishedAt": "2026-09-02T15:19:56.000Z",
    }

    job = parse_moka_job(
        detail_item,
        company="ANTA Group / 安踏集团",
        source_root="https://jobs.anta.com/social-recruitment/antahr/146041/",
    )

    assert job is not None
    assert job["source_job_id"] == "e105f85c-012a-43bb-9ca0-c48bc2a6a639"
    assert "上海" in job["location"]
    assert job["location_category"] == LocationCategory.CONFIRMED_SHANGHAI.value
