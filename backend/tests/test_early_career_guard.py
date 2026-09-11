from app.matching.early_career_guard import detect_early_career_markers


def test_detect_early_career_markers_for_alibaba_campus_signals():
    markers = detect_early_career_markers(
        [
            "安全技术工程师",
            "Graduation Dates: 2026-11-01 - 2027-10-31",
            "Hiring Program: Alibaba 2027 Graduate Recruitment",
            "https://campus-talent.alibaba.com/campus/position/199907620043",
        ]
    )

    assert "alibaba-campus-portal" in markers
    assert any("graduation\\s*dates?" in marker.lower() for marker in markers)
    assert "graduate recruitment" in markers


def test_detect_early_career_markers_empty_when_no_signals():
    markers = detect_early_career_markers(
        [
            "Lead Cyber Security Architect",
            "Own enterprise IAM and cloud security architecture.",
            "https://jobs.example.com/security-arch",
        ]
    )

    assert markers == []
