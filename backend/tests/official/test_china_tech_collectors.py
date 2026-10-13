import json
from datetime import datetime, timezone

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import Base
from app.models.job import Job
from app.official.collectors.alibaba import (
    ALIBABA_COMPANY,
    ALIYUN_COMPANY,
    ALIYUN_ROOT,
    AlibabaOfficialCollector,
    AliyunOfficialCollector,
    aliyun_position_url,
    parse_alibaba_position,
)
from app.official.collectors.bcg import parse_bcg_job
from app.official.collectors.feishu_jobs import parse_feishu_jobs
from app.official.collectors.huawei import parse_huawei_jobs
from app.official.collectors.midea import parse_midea_position
from app.official.collectors.moka import parse_moka_job
from app.official.collectors.tencent import parse_tencent_jobs
from app.official.location import LocationCategory
from app.pipeline import ingest_collector


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
    assert job["company"] == ALIBABA_COMPANY
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


def test_parses_aliyun_position_with_cloud_portal_url():
    job = parse_alibaba_position(
        _alibaba_social_item(
            id=100047500002,
            name="阿里云智能-技术服务工程师TAM-金融行业/AI智能体方向-北京/上海",
            workLocations=["北京", "上海"],
            experience={"from": 3, "to": None},
        ),
        root=ALIYUN_ROOT,
        company=ALIYUN_COMPANY,
    )

    assert job["company"] == ALIYUN_COMPANY
    assert job["location_category"] == LocationCategory.CONFIRMED_SHANGHAI.value
    assert "Experience: 3+ years" in job["description"]
    assert job["source_url"] == (
        "https://careers.aliyun.com/off-campus/position-detail?positionId=100047500002"
    )
    assert job["apply_url"] == job["source_url"]


def test_builds_aliyun_position_urls_per_language():
    assert aliyun_position_url("100046940001", "zh") == (
        "https://careers.aliyun.com/off-campus/position-detail?positionId=100046940001"
    )
    assert aliyun_position_url("100008423001", "en") == (
        "https://careers.aliyun.com/en/off-campus/position-detail?positionId=100008423001"
    )


def _mock_alibaba_platform(monkeypatch, datas_for):
    searches = []

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if request.method == "GET":
            assert request.url.path == "/off-campus/position-list"
            return httpx.Response(
                302,
                headers={
                    "set-cookie": f"XSRF-TOKEN=tok-{host}; Path=/",
                    "location": "/off-campus/home",
                },
            )
        assert request.url.path == "/position/search"
        assert request.headers["x-xsrf-token"] == f"tok-{host}"
        body = json.loads(request.content)
        assert request.headers["referer"] == (
            f"https://{host}/off-campus/position-list?lang={body['language']}"
        )
        searches.append((host, body))
        return httpx.Response(
            200, json={"success": True, "content": {"datas": datas_for(host, body)}}
        )

    real_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    return searches


def _search_signature(body):
    return (
        body["channel"],
        body["key"],
        body.get("subCategories"),
        body.get("regions"),
    )


def test_aliyun_collector_searches_cloud_portal_keywords_before_sweeps(monkeypatch):
    tam_shanghai = _alibaba_social_item(
        id=11, name="阿里云智能-技术服务工程师TAM-上海", workLocations=["上海"]
    )
    tam_hangzhou = _alibaba_social_item(
        id=100046940001,
        name="阿里云智能-技术服务工程师TAM-出海KA客户-杭州",
        workLocations=["杭州"],
    )

    def datas_for(host, body):
        assert host == "careers.aliyun.com"
        if body.get("regions") == "310100":
            return [_alibaba_social_item(id=10, workLocations=["上海"]), tam_shanghai]
        if body["key"] == "技术服务":
            return [tam_shanghai, tam_hangzhou]
        if body["language"] == "en" and body["key"] == "":
            return [
                _alibaba_social_item(id=20, workLocations=["Kuala Lumpur"]),
                _alibaba_social_item(id=21, workLocations=["Hong Kong, China"]),
            ]
        return []

    searches = _mock_alibaba_platform(monkeypatch, datas_for)

    jobs = AliyunOfficialCollector().fetch_raw()

    assert [_search_signature(body) for _, body in searches] == [
        ("group_official_site", "安全", None, None),
        ("group_official_site", "", "407", None),
        ("group_official_site", "技术服务", None, None),
        ("group_official_site", "解决方案", None, None),
        ("group_official_site", "架构师", None, None),
        ("group_overseas_official_site", "security", None, None),
        ("group_overseas_official_site", "architect", None, None),
        ("group_official_site", "", None, "310100"),
        ("group_overseas_official_site", "", None, None),
    ]
    assert [job["source_job_id"] for job in jobs] == ["11", "10", "20"]
    assert {job["company"] for job in jobs} == {ALIYUN_COMPANY}
    assert jobs[0]["source_url"] == (
        "https://careers.aliyun.com/off-campus/position-detail?positionId=11"
    )
    assert jobs[2]["source_url"] == (
        "https://careers.aliyun.com/en/off-campus/position-detail?positionId=20"
    )


def _handoff_datas(host, body):
    # Recent publish times keep these rows clear of the ingest max-age rule.
    published = int(datetime.now(timezone.utc).timestamp() * 1000)

    def item(**overrides):
        return _alibaba_social_item(publishTime=published, **overrides)

    cloud_shanghai = item(id=5, name="阿里云智能-云安全专家-上海", workLocations=["上海"])
    cloud_malaysia = item(
        id=2,
        name="Alibaba Cloud-Data Center Security Manager-Malaysia",
        workLocations=["Johor Bahru"],
    )
    if host == "careers.aliyun.com":
        if body.get("regions") == "310100":
            return [cloud_shanghai]
        if body["language"] == "en" and body["key"] == "":
            return [cloud_malaysia]
        return []
    assert host == "talent.alibaba.com"
    if body["language"] == "en":
        return [cloud_malaysia, item(id=3, workLocations=["Singapore"])]
    return [item(id=1), cloud_shanghai, item(id=4, workLocations=["北京"])]


def test_alibaba_collector_hands_alibaba_cloud_roles_to_aliyun(monkeypatch):
    searches = _mock_alibaba_platform(monkeypatch, _handoff_datas)

    collector = AlibabaOfficialCollector()
    jobs = collector.fetch_raw()

    assert [
        _search_signature(body) for host, body in searches if host == "talent.alibaba.com"
    ] == [
        ("group_official_site", "安全", None, None),
        ("group_official_site", "security", None, None),
        ("group_official_site", "", "407", None),
        ("group_overseas_official_site", "security", None, None),
        ("group_overseas_official_site", "", "407", None),
    ]
    assert [job["source_job_id"] for job in jobs] == ["1"]
    assert jobs[0]["company"] == ALIBABA_COMPANY
    assert jobs[0]["source_url"].startswith("https://talent.alibaba.com/")
    assert collector.retired_source_url_prefixes == (
        "https://campus-talent.alibaba.com",
        "https://talent.alibaba.com/en/off-campus/position-detail?positionId=2",
        "https://talent.alibaba.com/off-campus/position-detail?positionId=5",
    )


def test_ingest_moves_alibaba_cloud_rows_from_alibaba_to_aliyun_source(monkeypatch):
    _mock_alibaba_platform(monkeypatch, _handoff_datas)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    stored_cloud_url = "https://talent.alibaba.com/off-campus/position-detail?positionId=5"

    with Session(engine) as db:
        db.add(
            Job(
                source="official_alibaba",
                source_job_id="5",
                company="Alibaba / Alibaba Cloud",
                title="阿里云智能-云安全专家-上海",
                location="上海",
                country="China",
                description="负责云安全。",
                apply_url=stored_cloud_url,
                source_url=stored_cloud_url,
                posted_at=now,
                updated_at=now,
                first_seen_at=now,
                last_seen_at=now,
                content_hash="old",
                match_score=0,
                status="active",
                location_category="confirmed_shanghai",
            )
        )
        db.commit()

        ingest_collector(db, AlibabaOfficialCollector())
        ingest_collector(db, AliyunOfficialCollector())

        rows = {(job.source, job.source_job_id): job for job in db.query(Job).all()}

        assert rows[("official_alibaba", "5")].status == "closed"
        assert rows[("official_alibaba", "1")].status == "active"
        assert rows[("official_aliyun", "5")].status == "active"
        assert rows[("official_aliyun", "5")].source_url == (
            "https://careers.aliyun.com/off-campus/position-detail?positionId=5"
        )
        assert rows[("official_aliyun", "2")].country == "Malaysia"
        assert ("official_alibaba", "2") not in rows


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
