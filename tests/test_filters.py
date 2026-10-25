"""Unit tests for filters.py"""
import pytest
from jobfeed.filters import (
    check_eligibility, classify_employment, classify_work_type,
    extract_experience, extract_recruiter_email, is_us_location,
    make_title_matcher, suggested_profile,
)
from jobfeed.models import Job


def make_job(**kw) -> Job:
    defaults = dict(source="test", source_id="1", title="Data Engineer", company="Acme",
                    location="New York, NY", url="https://example.com/job/1",
                    description="", posted_at=None, employment_hint="", remote_hint="",
                    via_job_board=False, publisher="", description_complete=True)
    defaults.update(kw)
    return Job(**defaults)


# -------- title matcher --------

def test_title_match_basic():
    m = make_title_matcher(["data engineer", "etl"], ["intern", "director"])
    assert m("Senior Data Engineer")
    assert m("ETL Developer")
    assert not m("Data Entry Clerk")
    assert not m("Data Engineering Director")
    assert not m("Data Engineering Intern")


# -------- US location --------

def test_us_location():
    assert is_us_location("New York, NY")
    assert is_us_location("Austin, TX")
    assert is_us_location("Remote, US")
    assert is_us_location("United States")
    assert is_us_location("")          # unknown → keep
    assert is_us_location("Remote")   # remote → keep


def test_foreign_location():
    assert not is_us_location("London, UK")
    assert not is_us_location("Bangalore, India")
    assert not is_us_location("Toronto, Canada")


# -------- eligibility --------

ELIG_CFG = {"exclude_clearance": True, "exclude_citizenship_only": True,
             "exclude_itar_us_person": True, "exclude_no_sponsorship": False}


def test_clearance_excluded():
    j = make_job(description="Must have active Top Secret clearance.")
    assert check_eligibility(j, ELIG_CFG) is not None


def test_clearance_negated():
    j = make_job(description="No security clearance required for this role.")
    assert check_eligibility(j, ELIG_CFG) is None


def test_citizen_only_excluded():
    j = make_job(description="Must be a U.S. citizen to apply.")
    assert check_eligibility(j, ELIG_CFG) is not None


def test_citizen_or_authorized_passes():
    j = make_job(description="Must be a U.S. citizen or authorized to work in the US.")
    assert check_eligibility(j, ELIG_CFG) is None


def test_gc_only_excluded():
    j = make_job(description="Green card holders only, no sponsorship.")
    assert check_eligibility(j, ELIG_CFG) is not None


def test_itar_excluded():
    j = make_job(description="This role is subject to ITAR and requires a U.S. person.")
    assert check_eligibility(j, ELIG_CFG) is not None


def test_no_sponsor_flagged_not_excluded():
    j = make_job(description="We are unable to sponsor visas at this time.")
    reason = check_eligibility(j, ELIG_CFG)
    assert reason is None           # exclude_no_sponsorship=False → flag only
    assert j.sponsorship_note == "No sponsorship"


def test_sponsor_available_noted():
    j = make_job(description="We will sponsor H-1B visas for qualified candidates.")
    check_eligibility(j, ELIG_CFG)
    assert "available" in j.sponsorship_note


# -------- employment type --------

def test_classify_c2c():
    j = make_job(description="Open to C2C arrangements.")
    assert classify_employment(j) == "C2C / Contract"


def test_classify_w2():
    j = make_job(description="W-2 only, no C2C.", employment_hint="contract")
    assert classify_employment(j) == "W2 Contract"


def test_classify_fulltime():
    j = make_job(employment_hint="fulltime")
    assert classify_employment(j) == "Full-time"


def test_classify_contract_to_hire():
    j = make_job(description="6-month contract-to-hire engagement.")
    assert classify_employment(j) == "Contract-to-hire"


# -------- work type --------

def test_remote_from_location():
    j = make_job(location="Remote, USA")
    assert classify_work_type(j) == "remote"


def test_hybrid_from_description():
    j = make_job(description="This is a hybrid role, 2 days in office.")
    assert classify_work_type(j) == "hybrid"


def test_onsite():
    j = make_job(description="This position is fully on-site in our Chicago office.")
    assert classify_work_type(j) == "on-site"


# -------- experience --------

def test_extract_exp():
    j = make_job(description="Requires 3+ years of experience with Spark.")
    assert extract_experience(j) == 3


def test_extract_exp_range():
    j = make_job(description="5-8 years of data engineering experience required.")
    assert extract_experience(j) == 5


def test_extract_exp_none():
    j = make_job(description="No experience requirements stated.")
    assert extract_experience(j) is None


# -------- recruiter email --------

def test_extract_email():
    j = make_job(description="Send your resume to recruiter@techcorp.io for consideration.")
    assert extract_recruiter_email(j) == "recruiter@techcorp.io"


def test_ignore_noreply():
    j = make_job(description="Replies to noreply@company.com are not monitored.")
    assert extract_recruiter_email(j) == ""


# -------- profile suggestion --------

def test_suggested_profile():
    assert suggested_profile(2) == "3yr"
    assert suggested_profile(3) == "3yr"
    assert suggested_profile(4) == "5yr"
    assert suggested_profile(None) == ""
