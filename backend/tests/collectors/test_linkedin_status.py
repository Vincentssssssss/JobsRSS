import pytest

from app.collectors.linkedin_status import (
    PostingState,
    classify_guest_job_response,
    find_linkedin_closed_marker,
    linkedin_job_id,
)

# Trimmed from real https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{id}
# responses (October 2026).
OPEN_GUEST_PAGE = """
<section class="top-card-layout container-lined overflow-hidden babybear:rounded-[0px]">
  <div class="top-card-layout__card relative p-2 papabear:p-details-container-padding">
    <h2 class="top-card-layout__title font-sans text-lg topcard__title">Senior Offensive Security Consultant - Hong Kong</h2>
    <h4 class="top-card-layout__second-subline font-sans text-sm">
      <span class="posted-time-ago__text topcard__flavor--metadata">4 days ago</span>
      <figure class="num-applicants__figure topcard__flavor--metadata topcard__flavor--bullet">
        <figcaption class="num-applicants__caption">Be among the first 25 applicants</figcaption>
      </figure>
    </h4>
    <div class="top-card-layout__cta-container flex flex-wrap mt-0.5 papabear:mt-0 ml-[-12px]">
      <button class="apply-button apply-button--default top-card-layout__cta">Apply</button>
    </div>
  </div>
</section>
<div class="description__text description__text--rich">
  <div class="show-more-less-html__markup">Lead offensive security engagements.</div>
</div>
"""

CLOSED_GUEST_PAGE = """
<section class="top-card-layout container-lined overflow-hidden babybear:rounded-[0px]">
  <div class="top-card-layout__card relative p-2 papabear:p-details-container-padding">
    <h2 class="top-card-layout__title font-sans text-lg topcard__title">Water Quality - Data Quality Assistant - 29379</h2>
    <h4 class="top-card-layout__second-subline font-sans text-sm">
      <span class="posted-time-ago__text topcard__flavor--metadata">2 years ago</span>
      <figure class="closed-job closed-job__flavor topcard__flavor-row">
        <span class="closed-job__icon closed-job__icon--error-pebble lazy-load"></span>
        <figcaption class="closed-job__flavor--closed">{marker}</figcaption>
      </figure>
    </h4>
    <div class="top-card-layout__cta-container flex flex-wrap mt-0.5 papabear:mt-0 ml-[-12px]">
      <!-- --> <!-- -->
    </div>
  </div>
</section>
<div class="description__text description__text--rich">
  <div class="show-more-less-html__markup">Monitor water quality data.</div>
</div>
"""


@pytest.mark.parametrize(
    "marker",
    ["No longer accepting applications", "已停止接受求职申请", "不再受理應徵"],
)
def test_guest_closed_badge_is_detected_in_every_locale(marker):
    assert find_linkedin_closed_marker(CLOSED_GUEST_PAGE.format(marker=marker)) == marker


def test_open_guest_page_has_no_closed_marker():
    assert find_linkedin_closed_marker(OPEN_GUEST_PAGE) is None


@pytest.mark.parametrize(
    "snippet",
    [
        '<div class="artdeco-inline-feedback artdeco-inline-feedback--error">'
        '<span class="artdeco-inline-feedback__message">No longer accepting applications</span></div>',
        '<div class="jobs-details-top-card__apply-error"><span>不再接受申请</span></div>',
        "<main><h1>This job is no longer available</h1></main>",
    ],
)
def test_logged_in_layout_text_markers_are_detected(snippet):
    html = f"<html><body><h1>Principal Cloud Security Architect</h1>{snippet}</body></html>"

    assert find_linkedin_closed_marker(html) is not None


def test_marker_inside_description_or_scripts_is_ignored():
    html = """
    <html><body>
      <h1>Security Manager</h1>
      <button class="jobs-apply-button">Easy Apply</button>
      <div class="jobs-description__content">
        Once the requisition fills we are no longer accepting applications.
      </div>
      <script>window.i18n = {"closed": "No longer accepting applications"};</script>
      <code style="display:none">{"text":"已停止接受求职申请"}</code>
      <style>.closed-job { color: red; }</style>
    </body></html>
    """

    assert find_linkedin_closed_marker(html) is None


def test_marker_split_across_lines_is_detected():
    html = "<div><span>No longer accepting\n          applications</span></div>"

    assert find_linkedin_closed_marker(html) == "no longer accepting applications"


@pytest.mark.parametrize(
    ("candidates", "expected"),
    [
        (("https://www.linkedin.com/jobs/view/4451905595/",), "4451905595"),
        (("https://hk.linkedin.com/jobs/view/cloud-security-at-acme-4451905595?trk=x",), "4451905595"),
        (("https://www.linkedin.com/comm/jobs/view/4451905595/?trackingId=abc",), "4451905595"),
        (("https://www.linkedin.com/jobs/collections/recommended/?currentJobId=4451905595",), "4451905595"),
        (("", "4451905595"), "4451905595"),
        (("https://jobs.acme.com/jobs/view/4451905595/", "0123abcd" * 4), None),
        (("https://www.linkedin.com/jobs/search/?keywords=security",), None),
    ],
)
def test_linkedin_job_id_extraction(candidates, expected):
    assert linkedin_job_id(*candidates) == expected


def test_guest_response_with_closed_badge_is_closed():
    check = classify_guest_job_response(
        200, CLOSED_GUEST_PAGE.format(marker="No longer accepting applications")
    )

    assert check.state is PostingState.CLOSED
    assert check.reason == "marker:No longer accepting applications"


def test_guest_response_with_top_card_and_no_marker_is_open():
    assert classify_guest_job_response(200, OPEN_GUEST_PAGE).state is PostingState.OPEN


@pytest.mark.parametrize("status", [404, 410])
def test_removed_posting_is_closed(status):
    assert classify_guest_job_response(status, "").state is PostingState.CLOSED


def test_not_found_is_ambiguous_when_not_trusted():
    check = classify_guest_job_response(404, "", trust_not_found=False)

    assert check.state is PostingState.UNKNOWN


@pytest.mark.parametrize("status", [429, 999])
def test_throttling_is_never_a_verdict(status):
    body = CLOSED_GUEST_PAGE.format(marker="No longer accepting applications")

    assert classify_guest_job_response(status, body).state is PostingState.THROTTLED


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (200, "<html><body><script>var challenge = 1;</script></body></html>"),
        (200, '<html><body><form action="/uas/login">Sign in</form></body></html>'),
        (302, ""),
        (403, ""),
        (500, ""),
        (503, OPEN_GUEST_PAGE),
    ],
)
def test_ambiguous_responses_are_unknown(status, body):
    assert classify_guest_job_response(status, body).state is PostingState.UNKNOWN
