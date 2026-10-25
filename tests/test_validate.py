"""Unit tests for validate.py — uses unittest.mock to avoid real HTTP."""
from unittest.mock import MagicMock, patch

from jobfeed.models import Job
from jobfeed.validate import check_link, is_closed


def make_job(url="https://company.com/jobs/123", source="greenhouse", link_status=""):
    j = Job(source=source, source_id="1", title="Data Engineer", company="Acme",
            location="Remote", url=url, description="", posted_at=None,
            employment_hint="", remote_hint="", via_job_board=False, publisher="",
            description_complete=True)
    j.link_status = link_status
    return j


def fake_response(status=200, text="Apply now", url=None):
    r = MagicMock()
    r.status_code = status
    r.text = text
    r.url = url
    return r


def fake_session(response):
    s = MagicMock()
    s.get.return_value = response
    return s


def test_live_feed_skips_http():
    j = make_job(source="greenhouse")
    s = fake_session(fake_response())
    check_link(s, j)
    assert j.link_status == "open (live company feed)"
    s.get.assert_not_called()


def test_linkedin_unverified():
    j = make_job(url="https://linkedin.com/jobs/123", source="jsearch")
    check_link(fake_session(fake_response()), j)
    assert "unverified" in j.link_status


def test_404_closed():
    j = make_job(url="https://company.com/jobs/999", source="jsearch")
    check_link(fake_session(fake_response(status=404)), j)
    assert j.link_status == "closed (404)"


def test_redirect_to_careers_root():
    j = make_job(url="https://company.com/careers/jobs/123", source="jsearch")
    # Redirected to the careers root (shallow path)
    r = fake_response(url="https://company.com/careers")
    check_link(fake_session(r), j)
    assert j.link_status == "closed (redirected to careers home)"


def test_closed_text():
    j = make_job(url="https://company.com/jobs/123", source="jsearch")
    r = fake_response(text="This job is no longer accepting applications.")
    check_link(fake_session(r), j)
    assert j.link_status == "closed (page says no longer accepting)"


def test_open_job():
    j = make_job(url="https://company.com/jobs/123", source="jsearch")
    r = fake_response(text="Apply now! Great opportunity.")
    check_link(fake_session(r), j)
    assert j.link_status == "open"


def test_adzuna_url_upgraded():
    j = make_job(url="https://adzuna.com/land/ad/123", source="adzuna")
    j.via_job_board = True
    real_url = "https://company.greenhouse.io/jobs/456"
    r = fake_response(url=real_url)
    check_link(fake_session(r), j)
    assert j.url == real_url
    assert j.via_job_board is False   # is_direct_employer_link returns True for greenhouse


def test_already_decided():
    j = make_job(link_status="closed (404)")
    s = fake_session(fake_response())
    check_link(s, j)
    s.get.assert_not_called()


def test_is_closed():
    j = make_job(link_status="closed (404)")
    assert is_closed(j)
    j.link_status = "open"
    assert not is_closed(j)
