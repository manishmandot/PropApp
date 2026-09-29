import pytest

from propapp_pipeline.geo.allocate import Correspondence as C
from propapp_pipeline.geo.allocate import CorrespondenceIndex
from propapp_pipeline.geo.match import SuburbMatcher, normalise_name


@pytest.fixture
def m():
    idx = CorrespondenceIndex.from_rows([
        C("POA", "2549", "10070", 500, 1.0),
        C("POA", "2372", "10071", 400, 0.8),
        C("POA", "2372", "10099", 100, 0.2),
    ])
    return SuburbMatcher.from_rows([
        ("10050", "Mount Druitt", "NSW"),
        ("10060", "Paddington (NSW)", "NSW"),
        ("30060", "Paddington (Qld)", "QLD"),
        ("10070", "Bald Hills (Bega Valley - NSW)", "NSW"),
        ("10071", "Bald Hills (Tenterfield - NSW)", "NSW"),
    ], idx)


def test_normalise_name():
    assert normalise_name("  Mt   Druitt ") == "MOUNT DRUITT"
    assert normalise_name("Paddington (NSW)") == "PADDINGTON"
    assert normalise_name("Smithfield Mt") == "SMITHFIELD MOUNT"


def test_match_mt_and_suffix(m):
    assert m.match("MT DRUITT", "NSW") == "10050"
    assert m.match("PADDINGTON", "NSW") == "10060"
    assert m.match("Paddington", "QLD") == "30060"


def test_match_disambiguates_by_postcode(m):
    assert m.match("BALD HILLS", "NSW", "2549") == "10070"
    assert m.match("BALD HILLS", "NSW", "2372") == "10071"
    assert m.match("BALD HILLS", "NSW") is None
    assert m.match("BALD HILLS", "NSW", "9999") is None


def test_no_candidate(m):
    assert m.match("NOWHERE", "NSW", "2000") is None
