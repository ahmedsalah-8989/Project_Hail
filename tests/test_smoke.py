"""Smoke tests for project setup."""


def test_settings_load():
    from config.settings import HAIL_CITY_CENTER

    assert isinstance(HAIL_CITY_CENTER, tuple)
    assert len(HAIL_CITY_CENTER) == 2
