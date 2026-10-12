import json

import httpx

from app.official.collectors.alibaba import AlibabaOfficialCollector, parse_alibaba_position
from app.official.collectors.bcg import parse_bcg_job
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


def _alibaba_social_item(**overrides):
    item = {
        "id": 100032880001,
        "name": "淘宝闪购-应用安全专家-杭州/上海",
        "description": "负责应用安全体系建设。",
        "requirement": "熟悉 IAM、DevSecOps 与应用安全。",
        "workLocations": ["杭州", "上海"],
        "experience": {"from": 5, "to": None},
        "publishTime": 1791734400000,
        "modifyTime": 1791774007000,
        "positionUrl": (
            "/off-campus/position-detail?positionId=100032880001&track_id=SSP1"
        ),
    }
    item.update(overrides)
    return item


def test_parses_alibaba_social_position():
    job = parse_alibaba_position(_alibaba_social_item())

    assert job["source_job_id"] == "100032880001"
    assert job["location_category"] == LocationCategory.CONFIRMED_SHANGHAI.value
    assert job["country"] == "China"
    assert "DevSecOps" in job["description"]
    assert "Experience: 5+ years" in job["description"]
    assert job["posted_at"] == 1791734400000
    assert job["source_url"] == (
        "https://talent.alibaba.com/off-campus/position-detail?positionId=100032880001"
    )


def test_parses_alibaba_overseas_malaysia_position():
    job = parse_alibaba_position(
        _alibaba_social_item(
            id=100008423001,
            name="Alibaba Cloud-Data Center Security Manager-Malaysia",
            workLocations=["Johor Bahru"],
        ),
        language="en",
    )

    assert job["location_category"] == LocationCategory.CONFIRMED_MALAYSIA.value
    assert job["country"] == "Malaysia"
    assert job["source_url"] == (
        "https://talent.alibaba.com/en/off-campus/position-detail?positionId=100008423001"
    )


def test_skips_alibaba_position_outside_target_locations():
    assert parse_alibaba_position(_alibaba_social_item(workLocations=["北京", "杭州"])) is None


def test_alibaba_collector_searches_social_portal_with_xsrf(monkeypatch):
    searches = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            assert request.url.host == "talent.alibaba.com"
            return httpx.Response(
                302,
                headers={
                    "set-cookie": "XSRF-TOKEN=tok123; Path=/",
                    "location": "/off-campus/home",
                },
            )
        assert request.url == "https://talent.alibaba.com/position/search"
        assert request.headers["x-xsrf-token"] == "tok123"
        body = json.loads(request.content)
        searches.append((body["channel"], body["key"]))
        assert request.headers["referer"].endswith(f"lang={body['language']}")
        if body["channel"] == "group_overseas_official_site":
            datas = [
                _alibaba_social_item(id=2, workLocations=["Kuala Lumpur"]),
                _alibaba_social_item(id=3, workLocations=["Singapore"]),
            ]
        else:
            datas = [
                _alibaba_social_item(id=1),
                _alibaba_social_item(id=4, workLocations=["北京"]),
            ]
        return httpx.Response(
            200, json={"success": True, "content": {"totalCount": 2, "datas": datas}}
        )

    real_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )

    collector = AlibabaOfficialCollector()
    jobs = collector.fetch_raw()

    assert searches == [
        ("group_official_site", "安全"),
        ("group_official_site", "security"),
        ("group_overseas_official_site", "security"),
    ]
    assert [job["source_job_id"] for job in jobs] == ["1", "2"]
    assert all(job["source_url"].startswith("https://talent.alibaba.com/") for job in jobs)
    assert collector.retired_source_url_prefixes == ("https://campus-talent.alibaba.com",)


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


def test_parses_bcg_phenom_shanghai_job():
    listing = {
        "jobId": "52752",
        "jobSeqNo": "BCG1US52752EXTERNALENGLOBAL",
        "title": "Experienced Hire, Full-time, Greater China",
        "location": "Shanghai, Greater China",
        "postedDate": "2026-09-01T00:00:00.000+0000",
        "applyUrl": "https://experiencedtalent.bcg.com/careerhub/explore/jobs/790301457635",
    }
    detail = {
        "jobDetail": {
            "data": {
                "job": {
                    "companyName": "Boston Consulting Group",
                    "title": "Experienced Hire, Full-time, Greater China",
                    "location": "Shanghai, Greater China",
                    "description": (
                        "<p>Join BCG consulting teams in Shanghai to support "
                        "cloud security and IAM transformation programs.</p>"
                    ),
                    "postedDate": "2026-09-01T00:00:00.000+0000",
                    "applyUrl": listing["applyUrl"],
                    "jobSeqNo": "BCG1US52752EXTERNALENGLOBAL",
                }
            }
        }
    }

    job = parse_bcg_job(listing, detail)

    assert job["source_job_id"] == "BCG1US52752EXTERNALENGLOBAL"
    assert job["location_category"] == LocationCategory.CONFIRMED_SHANGHAI.value
    assert "IAM" in job["description"]
    assert job["source_url"].startswith("https://careers.bcg.com/global/en/job/")


def test_bcg_multi_location_role_is_kept_when_any_site_is_malaysia():
    listing = {
        "jobId": "59506",
        "jobSeqNo": "BCG1US59506EXTERNALENGLOBAL",
        "title": "Project Leader to Partner, Insurance Practice",
        "location": "Jakarta, Indonesia",
        "multi_location": [
            "Jakarta, Indonesia",
            "Kuala Lumpur, Wilayah Persekutuan Kuala Lumpur, Malaysia",
            "Bangkok, Bangkok, Thailand",
        ],
    }
    detail = {
        "jobDetail": {
            "data": {
                "job": {
                    "title": listing["title"],
                    "location": "Jakarta, Indonesia",
                    "description": "<p>Lead insurance cases.</p>",
                }
            }
        }
    }

    job = parse_bcg_job(listing, detail)

    assert job["location_category"] == LocationCategory.CONFIRMED_MALAYSIA.value
    assert job["country"] == "Malaysia"
    assert "Kuala Lumpur" in job["location"]


def test_parses_kpmg_moka_detail_with_city_id_only():
    detail_item = {
        "id": "87db5020-8673-42f9-a8f5-0b7e983f19cc",
        "title": "Cyber Security Manager",
        "jobDescription": "<p>负责网络安全咨询与攻防演练。</p>",
        "locations": [
            {
                "country": "中国",
                "cityId": 310112,
                "address": "申长路988弄虹桥万科中心",
            }
        ],
        "publishedAt": "2026-09-02T15:19:56.000Z",
    }

    job = parse_moka_job(
        detail_item,
        company="KPMG / 毕马威",
        source_root="https://app.mokahr.com/social-recruitment/kpmg/68240",
    )

    assert job is not None
    assert "上海" in job["location"]
    assert job["location_category"] == LocationCategory.CONFIRMED_SHANGHAI.value
