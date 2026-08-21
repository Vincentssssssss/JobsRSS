from app.official.collectors.beisen import parse_beisen_jobs
from app.official.collectors.hotjob import parse_hotjob_detail
from app.official.collectors.fosun import (
    _discover_fosun_links,
    parse_fosun_detail,
)
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


def test_parses_yunnan_baiyao_hotjob_detail():
    payload = {
        "data": {
            "postId": "6a670472e05c792b8ecf99a6",
            "postName": "信息安全经理",
            "company": "云南白药集团",
            "workPlaceStr": "上海市",
            "workContent": "负责集团云安全和应用安全建设。",
            "serviceCondition": "具备 IAM 与 DevSecOps 经验。",
            "publishDate": "2026-08-20 10:00:00",
        }
    }

    job = parse_hotjob_detail(payload)

    assert job["source_job_id"] == "6a670472e05c792b8ecf99a6"
    assert job["company"] == "云南白药集团"
    assert job["location_category"] == LocationCategory.CONFIRMED_SHANGHAI.value


def test_parses_fosun_server_rendered_detail():
    html = """
    <div class="xqbox">
      <h2>信息安全负责人(J10001)</h2>
      <div class="xqt"><ul>
        <li>成员公司：复星医药</li>
        <li>发布时间：2026-08-20</li>
        <li>工作地点：上海市</li>
      </ul></div>
      <div class="zwxqm">
        <h3>工作职责</h3><p>负责云安全和应用安全体系。</p>
        <h3>任职资格</h3><p>熟悉 IAM 和 DevSecOps。</p>
      </div>
    </div>
    """

    job = parse_fosun_detail(
        html,
        "https://fosunpharma.zhiye.com/socialxq?jobId=561287805",
    )

    assert job["source_job_id"] == "561287805"
    assert job["company"] == "复星医药"
    assert job["location_category"] == LocationCategory.CONFIRMED_SHANGHAI.value


def test_fosun_discovery_rejects_external_job_shaped_url():
    html = (
        '<a href="http://169.254.169.254/socialxq?jobId=123">'
        "fake job</a>"
    )

    assert _discover_fosun_links(html) == []
