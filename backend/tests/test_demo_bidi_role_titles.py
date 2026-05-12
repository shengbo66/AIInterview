# backend/tests/test_demo_bidi_role_titles.py
"""Unit tests for _COMPANY_ROLE_TITLES mapping in demo_bidi router."""
from app.routers.demo_bidi import _COMPANY_ROLE_TITLES, ROLE_TITLE


def test_tcl_maps_to_embodied_ai_architect():
    assert _COMPANY_ROLE_TITLES["TCL"] == "Embodied AI Architect"


def test_company_maps_to_rf_intern():
    assert "H公司" in _COMPANY_ROLE_TITLES
    assert _COMPANY_ROLE_TITLES["H公司"] == ROLE_TITLE


def test_unknown_company_falls_back_to_role_title():
    """get() with fallback must return ROLE_TITLE for unknown company names."""
    result = _COMPANY_ROLE_TITLES.get("未知公司", ROLE_TITLE)
    assert result == ROLE_TITLE


def test_all_mapped_titles_are_non_empty():
    for company, title in _COMPANY_ROLE_TITLES.items():
        assert title, f"empty role title for company: {company}"
