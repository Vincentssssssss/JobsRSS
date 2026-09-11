from app.presentation.description_sections import split_description_sections


def test_split_description_sections_with_chinese_headers():
    description = (
        "岗位职责：\n"
        "- 负责云安全体系建设\n"
        "- 推进威胁检测能力\n\n"
        "任职要求：\n"
        "- 5年以上安全经验\n"
        "- 熟悉IAM与零信任\n\n"
        "加分项：\n"
        "- 有跨国团队协作经验"
    )

    sections = split_description_sections(description)

    assert [section.title for section in sections] == ["岗位职责", "任职要求", "加分项"]
    assert sections[0].lines == ["负责云安全体系建设", "推进威胁检测能力"]
    assert sections[1].lines == ["5年以上安全经验", "熟悉IAM与零信任"]


def test_split_description_sections_falls_back_to_summary_block():
    description = "负责平台稳定性治理与跨团队协作，推动技术规划。"

    sections = split_description_sections(description)

    assert len(sections) == 1
    assert sections[0].title == "岗位概览"
    assert sections[0].lines == ["负责平台稳定性治理与跨团队协作，推动技术规划。"]
