from dataclasses import dataclass


@dataclass(frozen=True)
class OfficialSourceSpec:
    source_id: str
    company: str
    category: str
    career_url: str
    enabled: bool = False
    wave: int = 2
    collection_method: str = "assessment_pending"


FIRST_WAVE_SOURCE_IDS = {
    "amazon_aws",
    "google",
    "microsoft",
    "alibaba",
    "tencent",
    "huawei",
    "xiaomi",
    "bytedance",
    "wuxi_apptec",
    "wuxi_biologics",
    "hengrui",
    "fosun_pharma",
    "ct_tianqing",
    "yunnan_baiyao",
    "gsk",
    "roche",
}


def _source(
    source_id: str,
    company: str,
    category: str,
    career_url: str,
    collection_method: str = "assessment_pending",
) -> OfficialSourceSpec:
    enabled = source_id in FIRST_WAVE_SOURCE_IDS
    return OfficialSourceSpec(
        source_id=source_id,
        company=company,
        category=category,
        career_url=career_url,
        enabled=enabled,
        wave=1 if enabled else 2,
        collection_method=collection_method,
    )


OFFICIAL_SOURCE_REGISTRY = [
    _source(
        "amazon_aws",
        "Amazon / AWS",
        "technology",
        "https://www.amazon.jobs/",
        "json",
    ),
    _source(
        "google",
        "Google",
        "technology",
        "https://www.google.com/about/careers/applications/jobs/results/",
        "server_rendered_html",
    ),
    _source(
        "microsoft",
        "Microsoft",
        "technology",
        "https://apply.careers.microsoft.com/careers",
        "json",
    ),
    _source("alibaba", "Alibaba / Alibaba Cloud", "technology", "https://www.alibabagroup.com/careers"),
    _source(
        "tencent",
        "Tencent / Tencent Cloud",
        "technology",
        "https://careers.tencent.com/",
        "json",
    ),
    _source(
        "huawei",
        "Huawei / Huawei Cloud",
        "technology",
        "https://career.huawei.com/",
        "json",
    ),
    _source(
        "xiaomi",
        "Xiaomi",
        "technology",
        "https://career.mi.com/jobs",
        "json",
    ),
    _source(
        "bytedance",
        "ByteDance",
        "technology",
        "https://jobs.bytedance.com/experienced/position",
        "json",
    ),
    _source("apple", "Apple", "technology", "https://jobs.apple.com/"),
    _source("sap", "SAP", "technology", "https://jobs.sap.com/"),
    _source("gsk", "GSK", "pharma", "https://jobs.gsk.com/"),
    _source(
        "roche",
        "Roche",
        "pharma",
        "https://careers.roche.com/global/en/search-results",
        "json",
    ),
    _source("astrazeneca", "AstraZeneca", "pharma", "https://careers.astrazeneca.com/"),
    _source("novartis", "Novartis", "pharma", "https://www.novartis.com/careers"),
    _source("wuxi_apptec", "WuXi AppTec / 药明康德", "cro_cdmo", "https://www.wuxiappteccareers.com/jobs/"),
    _source("wuxi_biologics", "WuXi Biologics / 药明生物", "cro_cdmo", "https://www.wuxibiologics.com/join-us/"),
    _source("hengrui", "Hengrui Medicine / 恒瑞医药", "pharma", "https://www.hengrui.com/"),
    _source("fosun_pharma", "Fosun Pharma / 复星医药", "pharma", "https://www.fosunpharma.com/"),
    _source("ct_tianqing", "Chia Tai Tianqing / 正大天晴", "pharma", "https://www.cttq.com/"),
    _source("yunnan_baiyao", "Yunnan Baiyao / 云南白药", "pharma", "https://www.yunnanbaiyao.com.cn/"),
    _source("hansoh", "Hansoh Pharma / 翰森制药", "pharma", "https://www.hspharm.com/"),
    _source("qilu_pharma", "Qilu Pharmaceutical / 齐鲁制药", "pharma", "https://www.qilu-pharma.com/"),
    _source("yangtze_river", "Yangtze River Pharmaceutical / 扬子江药业", "pharma", "https://www.yangzijiang.com/"),
    _source("junshi", "Junshi Biosciences / 君实生物", "biotech", "https://www.junshipharma.com/"),
    _source("henlius", "Henlius / 复宏汉霖", "biotech", "https://www.henlius.com/"),
    _source("zai_lab", "Zai Lab / 再鼎医药", "biotech", "https://www.zailaboratory.com/careers/"),
    _source("innovent", "Innovent Biologics / 信达生物", "biotech", "https://www.innoventbio.com/"),
    _source("beone", "BeOne Medicines / 百济神州", "biotech", "https://careers.beonemedicines.com/"),
    _source("akeso", "Akeso / 康方生物", "biotech", "https://www.akesobio.com/"),
    _source("remgen", "RemeGen / 荣昌生物", "biotech", "https://www.remegen.com/"),
    _source("kelun", "Kelun / 科伦药业与科伦博泰", "pharma", "https://www.kelun.com/"),
    _source("simcere", "Simcere / 先声药业", "pharma", "https://www.simcere.com/"),
    _source("huadong_medicine", "Huadong Medicine / 华东医药", "pharma", "https://www.eastchinapharm.com/"),
    _source("hutchmed", "HUTCHMED / 和黄医药", "biotech", "https://www.hutch-med.com/careers/"),
    _source("tigermed", "Tigermed / 泰格医药", "cro_cdmo", "https://www.tigermedgrp.com/"),
    _source("pharmaron", "Pharmaron / 康龙化成", "cro_cdmo", "https://www.pharmaron.com/careers/"),
    _source("asychem", "Asymchem / 凯莱英", "cro_cdmo", "https://www.asymchem.com/"),
    _source("porton", "Porton Pharma / 博腾股份", "cro_cdmo", "https://www.portonpharma.com/"),
]

OFFICIAL_SOURCE_BY_ID = {
    source.source_id: source for source in OFFICIAL_SOURCE_REGISTRY
}


def get_official_source(source_id: str) -> OfficialSourceSpec:
    try:
        return OFFICIAL_SOURCE_BY_ID[source_id]
    except KeyError as exc:
        raise ValueError(f"Unknown official source: {source_id}") from exc
