from app.core.config import Settings
from app.matching.scorer import score_job


def test_adjacent_cloud_roles_reach_the_llm_threshold():
    min_rule_score = Settings().llm_min_rule_score
    for title, location in [
        ("阿里云智能-技术服务工程师TAM-出海KA客户-杭州", "杭州"),
        ("Solutions Architect, AWS", "Hong Kong"),
        ("Customer Engineer, Infrastructure Modernization", "Singapore"),
        ("售前解决方案专家", "苏州"),
    ]:
        assert score_job(title, "", location) >= min_rule_score, title


def test_security_roles_outscore_adjacent_roles():
    security = score_job("Information Security Manager", "", "Shanghai")
    adjacent = score_job("Solutions Architect Manager", "", "Shanghai")

    assert security > adjacent > 0


def test_new_target_locations_earn_the_location_bonus():
    base = score_job("Security Architect", "", "Beijing")
    for location in ("Hangzhou, Zhejiang", "Suzhou", "Hong Kong SAR", "Singapore"):
        assert score_job("Security Architect", "", location) == base + 15, location


def test_early_career_roles_score_zero():
    assert score_job("Security Engineer Intern", "", "Shanghai") == 0
