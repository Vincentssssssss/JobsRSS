import base64
import json

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.official.collectors.moka import decrypt_moka_response, parse_moka_job
from app.official.collectors.roche import parse_roche_job
from app.official.location import LocationCategory


def test_parses_roche_phenom_detail_job():
    listing = {
        "jobId": "202608-120483",
        "jobSeqNo": "ROCHGLOBAL202608120483EXTERNALENGLOBAL",
        "title": "Security Transformation Lead",
        "location": "Shanghai, Shanghai, China's Mainland",
        "postedDate": "2026-08-20T00:00:00.000+0000",
        "applyUrl": "https://roche.wd3.myworkdayjobs.com/roche-ext/job/Shanghai/job/apply",
    }
    detail = {
        "jobDetail": {
            "data": {
                "job": {
                    "companyName": "Roche",
                    "structureData": {
                        "@type": "JobPosting",
                        "title": "Security Transformation Lead",
                        "description": (
                            "<p>Lead cloud security, IAM, and application security "
                            "transformation across China.</p>"
                        ),
                        "datePosted": "2026-08-20",
                        "jobLocation": {
                            "address": {
                                "addressLocality": "Shanghai",
                                "addressRegion": "Shanghai",
                                "addressCountry": "China's Mainland",
                            }
                        },
                    },
                }
            }
        }
    }

    job = parse_roche_job(listing, detail)

    assert job["source_job_id"] == listing["jobSeqNo"]
    assert job["company"] == "Roche"
    assert job["location_category"] == LocationCategory.CONFIRMED_SHANGHAI.value
    assert "IAM" in job["description"]


def test_decrypts_and_parses_moka_job():
    key = "1234567890abcdef"
    iv = "abcdef1234567890"
    plaintext = {
        "code": 0,
        "data": {
            "id": "5666b34e-334f-4c08-b8bc-1c049ed7ec55",
            "title": "Cloud Security Lead",
            "jobDescription": "Lead cloud security, IAM, and DevSecOps.",
            "locations": [{"cityName": "上海", "provinceName": "上海"}],
            "publishedAt": "2026-08-20T00:00:00Z",
        },
    }
    padder = padding.PKCS7(128).padder()
    padded = padder.update(json.dumps(plaintext).encode()) + padder.finalize()
    encryptor = Cipher(
        algorithms.AES(key.encode()), modes.CBC(iv.encode())
    ).encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()

    decoded = decrypt_moka_response(
        {
            "data": base64.b64encode(encrypted).decode(),
            "necromancer": key,
        },
        iv,
    )
    job = parse_moka_job(
        decoded["data"],
        company="GSK",
        source_root="https://app.mokahr.com/social-recruitment/gsk/148067",
    )

    assert job["company"] == "GSK"
    assert job["location_category"] == LocationCategory.CONFIRMED_SHANGHAI.value
