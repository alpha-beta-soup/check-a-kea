from unittest.mock import MagicMock

from core.session import ValidationSession


def session(fids):
    return ValidationSession(layer=MagicMock(), feature_ids=fids)


def test_len():
    assert len(session([10, 20, 30])) == 3


def test_current_fid_starts_at_first():
    assert session([10, 20, 30]).current_fid == 10


def test_navigate_forward():
    s = session([10, 20, 30])
    assert s.navigate(1) is True
    assert s.index == 1
    assert s.current_fid == 20


def test_navigate_backward():
    s = session([10, 20, 30])
    s.index = 2
    assert s.navigate(-1) is True
    assert s.index == 1


def test_navigate_past_end_returns_false():
    s = session([10, 20, 30])
    s.index = 2
    assert s.navigate(1) is False
    assert s.index == 2


def test_navigate_before_start_returns_false():
    s = session([10, 20, 30])
    assert s.navigate(-1) is False
    assert s.index == 0


def test_clamp_index_too_high():
    s = session([10, 20, 30])
    s.index = 99
    s.clamp_index()
    assert s.index == 2


def test_clamp_index_negative():
    s = session([10, 20, 30])
    s.index = -5
    s.clamp_index()
    assert s.index == 0


def test_index_of_existing_fid():
    s = session([10, 20, 30])
    assert s.index_of(20) == 1


def test_index_of_missing_fid_returns_none():
    s = session([10, 20, 30])
    assert s.index_of(99) is None
