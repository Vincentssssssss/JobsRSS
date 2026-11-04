import httpx

from app.official.collectors.beisen import parse_beisen_jobs
from app.official.collectors.catalog import official_fixed_companies
from app.official.collectors.hotjob import (
    HOTJOB_USER_AGENT,
    DeloitteOfficialCollector,
    SimcereOfficialCollector,
    YunnanBaiyaoOfficialCollector,
    parse_hotjob_detail,
)
from app.official.collectors.fosun import FosunPharmaOfficialCollector
from app.official.location import LocationCategory


def test_parses_beisen_pharma_jobs():
    payload = {
        "Data": [
            {
                "Id": "058e196f-e074-4a94-b24b-346e80f4c623",
                "JobAdId": 511183316,
                "JobAdName": "云平台安全工程师",
                "LocNames": ["上海市"],
                "Duty": "负责药物研发平台的云安全控制。",
                "Require": "熟悉 IAM、DevSecOps 与应用安全。",
                "PostDate": "0001-01-01T00:00:00",
                "ChangeDate": "2026-08-20T10:05:23",
            }
        ]
    }

    jobs = parse_beisen_jobs(
        payload,
        company="WuXi AppTec / 药明康德",
        portal_root="https://wuxiapptec.zhiye.com",
    )

    assert len(jobs) == 1
    assert jobs[0]["source_job_id"] == "058e196f-e074-4a94-b24b-346e80f4c623"
    assert jobs[0]["posted_at"] == "2026-08-20T10:05:23"
    assert jobs[0]["location_category"] == LocationCategory.CONFIRMED_SHANGHAI.value


def test_parses_yunnan_baiyao_hotjob_detail_ignoring_the_business_unit_company_field():
    payload = {
        "data": {
            "postId": "6a670472e05c792b8ecf99a6",
            "postName": "信息安全经理",
            "company": "药品事业群",
            "workPlaceStr": "上海市",
            "workContent": "负责集团云安全和应用安全建设。",
            "serviceCondition": "具备 IAM 与 DevSecOps 经验。",
            "publishDate": "2026-08-20 10:00:00",
        }
    }

    job = parse_hotjob_detail(payload, company="Yunnan Baiyao / 云南白药")

    assert job["source_job_id"] == "6a670472e05c792b8ecf99a6"
    assert job["company"] == "Yunnan Baiyao / 云南白药"
    assert job["location_category"] == LocationCategory.CONFIRMED_SHANGHAI.value


def test_parses_simcere_hotjob_detail_with_company_and_tenant():
    payload = {
        "data": {
            "postId": "6a8d42321ad6db7cf83bc51d",
            "postName": "网络安全专家",
            "workPlaceStr": "上海市",
            "workContent": "负责企业安全架构建设。",
            "serviceCondition": "熟悉 IAM 与 SOC。",
            "publishDate": "2026-08-20 10:00:00",
        }
    }

    job = parse_hotjob_detail(
        payload,
        company="Simcere / 先声药业",
        tenant="SU61458d83bef57c54dcb4e43f",
    )

    assert job["company"] == "Simcere / 先声药业"
    assert "SU61458d83bef57c54dcb4e43f" in job["source_url"]
    assert job["location_category"] == LocationCategory.CONFIRMED_SHANGHAI.value


def test_parses_deloitte_hotjob_detail_on_custom_host():
    payload = {
        "data": {
            "postId": "6a9939a79e5f824145243a1b",
            "postName": "Cyber Risk Consultant",
            "company": "中国大陆",
            "workPlaceStr": "上海市",
            "workContent": "负责客户网络安全咨询项目。",
            "serviceCondition": "熟悉 IAM 与云安全。",
            "publishDate": "2026-09-03 17:10:49",
        }
    }

    job = parse_hotjob_detail(
        payload,
        company="Deloitte / 德勤",
        tenant="SU649e304a6a9f0ef690533e9a",
        api_root="https://ehjobs.deloitte.com.cn",
    )

    assert job["company"] == "Deloitte / 德勤"
    assert job["source_url"].startswith("https://ehjobs.deloitte.com.cn/")
    assert job["location_category"] == LocationCategory.CONFIRMED_SHANGHAI.value


def test_fosun_uses_the_beisen_api_and_retires_old_server_rendered_rows(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "Count": 1,
                "Data": [
                    {
                        "Id": "ba857293-fea4-4360-99b8-d2c5c8c0a86d",
                        "JobAdName": "信息安全高级经理(J15113)",
                        "LocNames": ["上海市"],
                        "Duty": "负责集团云安全和应用安全体系。",
                        "Require": "熟悉 IAM 和 DevSecOps。",
                        "PostDate": "2026-10-26T19:51:01",
                    }
                ],
            },
        )

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client
    monkeypatch.setattr(
        "app.official.collectors.beisen.httpx.Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )
    collector = FosunPharmaOfficialCollector()

    jobs = collector.collect()

    assert str(requests[0].url) == "https://fosunpharma.zhiye.com/api/Jobad/GetJobAdPageList"
    assert len(jobs) == 1
    assert jobs[0].company == "Fosun Pharma / 复星医药"
    assert jobs[0].source_url == (
        "https://fosunpharma.zhiye.com/social/detail?jobAdId=ba857293-fea4-4360-99b8-d2c5c8c0a86d"
    )
    assert collector.retired_source_url_prefixes == ("https://fosunpharma.zhiye.com/socialxq",)
    assert not jobs[0].source_url.startswith(collector.retired_source_url_prefixes)


def test_hotjob_collectors_store_their_own_name_even_if_raw_company_differs():
    collector = DeloitteOfficialCollector()
    job = collector.normalize(
        {
            "source_job_id": "6a9939a79e5f824145243a1b",
            "company": "中国大陆",
            "title": "Senior Manager - Cyber Defense & Resilience- Shanghai",
            "location": "上海市",
            "source_url": "https://ehjobs.deloitte.com.cn/x",
            "content_hash": "hash",
            "location_category": LocationCategory.CONFIRMED_SHANGHAI.value,
        }
    )

    assert job.company == "Deloitte / 德勤"


def test_catalog_lists_fixed_company_names_for_hotjob_sources():
    fixed = official_fixed_companies()

    assert fixed["official_deloitte"] == DeloitteOfficialCollector().fixed_company == "Deloitte / 德勤"
    assert fixed["official_yunnan_baiyao"] == YunnanBaiyaoOfficialCollector().fixed_company
    assert fixed["official_simcere"] == SimcereOfficialCollector().fixed_company
    assert "official_amazon_aws" not in fixed


def test_hotjob_sends_a_full_browser_user_agent():
    assert "AppleWebKit" in HOTJOB_USER_AGENT
