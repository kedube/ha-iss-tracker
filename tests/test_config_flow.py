"""Tests for the config and options flows."""

from __future__ import annotations

import re
from unittest.mock import patch

from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.const import (
    CONF_ELEVATION,
    CONF_LATITUDE,
    CONF_LOCATION,
    CONF_LONGITUDE,
    CONF_NAME,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from homeassistant.helpers.selector import LocationSelector
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
import voluptuous as vol

from custom_components.iss_tracker.const import (
    CONF_ALERT_LEAD_MINUTES,
    CONF_FORECAST_DAYS,
    CONF_MAX_SUN_ELEVATION,
    CONF_MIN_ELEVATION,
    CONF_MIN_PEAK_ELEVATION,
    CONF_MIN_VISIBLE_DURATION,
    CONF_N2YO_API_KEY,
    CONF_SHOW_CALENDAR,
    CONF_SHOW_PANEL,
    CONF_UNITS,
    DOMAIN,
)

LINE1 = "1 25544U 98067A   26281.85354122  .00006592  00000+0  12863-3 0  9993"
LINE2 = "2 25544  51.6315  97.5838 0006777 239.2205 120.8116 15.48782232589376"

OPTIONS = {
    CONF_MIN_ELEVATION: 10,
    CONF_MIN_PEAK_ELEVATION: 25,
    CONF_MAX_SUN_ELEVATION: -4,
    CONF_MIN_VISIBLE_DURATION: 120,
    CONF_FORECAST_DAYS: 7,
    CONF_ALERT_LEAD_MINUTES: 30,
}


def _selector_checks_range() -> bool:
    """Whether the location selector refuses coordinates out of range itself.

    It does from Home Assistant 2026.11: the flow never sees them, and the form
    shows the selector's error. Its map brings a longitude into range before
    sending it. Older versions leave both to the flow, which refuses a latitude
    and brings a longitude into range.
    """
    try:
        LocationSelector()({CONF_LATITUDE: 95.0, CONF_LONGITUDE: 0.0})
    except vol.Invalid:
        return True
    return False


SELECTOR_CHECKS_RANGE = _selector_checks_range()
WRAPPED = pytest.mark.skipif(
    SELECTOR_CHECKS_RANGE, reason="the location selector refuses longitudes beyond 180"
)


def _user_input(lat: float = 42.36012345, lon: float = -71.0589) -> dict:
    return {
        CONF_NAME: "Backyard",
        CONF_LOCATION: {CONF_LATITUDE: lat, CONF_LONGITUDE: lon},
        CONF_ELEVATION: 12,
    }


async def test_user_flow(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM

    with patch("custom_components.iss_tracker.async_setup_entry", return_value=True) as setup:
        result = await hass.config_entries.flow.async_configure(result["flow_id"], _user_input())
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Backyard"
    assert result["data"] == {
        CONF_LATITUDE: 42.36012,
        CONF_LONGITUDE: -71.0589,
        CONF_ELEVATION: 12.0,
    }
    assert setup.call_count == 1


async def test_duplicate_location_aborts(hass: HomeAssistant) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id="42.360_-71.059").add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _user_input(42.3601, -71.0590)
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.parametrize("latitude", [423.601, -95.0, 90.0001, float("nan")])
async def test_out_of_range_latitude_is_refused(hass: HomeAssistant, latitude: float) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    if SELECTOR_CHECKS_RANGE:
        with pytest.raises(InvalidData):
            await hass.config_entries.flow.async_configure(
                result["flow_id"], _user_input(lat=latitude)
            )
    else:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _user_input(lat=latitude)
        )
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {CONF_LOCATION: "invalid_location"}
        # What was typed is kept, so only the location needs correcting.
        suggested = {
            str(key): key.description["suggested_value"]
            for key in result["data_schema"].schema
            if key.description and "suggested_value" in key.description
        }
        assert suggested[CONF_NAME] == "Backyard"
        assert suggested[CONF_ELEVATION] == 12

    with patch("custom_components.iss_tracker.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _user_input(lat=42.36)
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_LATITUDE] == 42.36


@pytest.mark.parametrize(
    ("longitude", "expected"),
    [
        pytest.param(288.94, -71.06, marks=WRAPPED),
        pytest.param(-431.06, -71.06, marks=WRAPPED),
        (180.0, 180.0),
        (-180.0, -180.0),
        (179.99999, 179.99999),
    ],
)
async def test_longitude_is_normalised(
    hass: HomeAssistant, longitude: float, expected: float
) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    with patch("custom_components.iss_tracker.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _user_input(lon=longitude)
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_LONGITUDE] == expected
    assert result["result"].unique_id == f"42.360_{expected:.3f}"


@WRAPPED
@pytest.mark.parametrize("longitude", [288.94, -431.06])
async def test_wrapped_longitude_is_a_duplicate(hass: HomeAssistant, longitude: float) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id="42.360_-71.060").add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _user_input(lon=longitude)
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


def _reconfigure_input(lat: float, lon: float, elevation: float = 40) -> dict:
    return {CONF_LOCATION: {CONF_LATITUDE: lat, CONF_LONGITUDE: lon}, CONF_ELEVATION: elevation}


async def test_reconfigure_moves_the_location(hass: HomeAssistant) -> None:
    """Correcting the coordinates keeps the entry, so cards bound to it keep working."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Backyard",
        data={CONF_LATITUDE: 42.36, CONF_LONGITUDE: -71.06, CONF_ELEVATION: 12.0},
        unique_id="42.360_-71.060",
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    if SELECTOR_CHECKS_RANGE:
        with pytest.raises(InvalidData):
            await hass.config_entries.flow.async_configure(
                result["flow_id"], _reconfigure_input(95, -71.06)
            )
    else:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _reconfigure_input(95, -71.06)
        )
        assert result["errors"] == {CONF_LOCATION: "invalid_location"}

    # Typed 0-360 where the selector lets that through.
    longitude = -71.05 if SELECTOR_CHECKS_RANGE else 288.95
    with patch("custom_components.iss_tracker.async_setup_entry", return_value=True) as setup:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _reconfigure_input(42.35, longitude)
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == {CONF_LATITUDE: 42.35, CONF_LONGITUDE: -71.05, CONF_ELEVATION: 40.0}
    assert entry.unique_id == "42.350_-71.050"
    assert entry.title == "Backyard"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    # Not loaded, so nothing else would pick the change up: it is set up now.
    assert setup.call_count == 1


async def test_reconfigure_keeps_the_place_or_refuses_a_duplicate(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_LATITUDE: 42.36, CONF_LONGITUDE: -71.06, CONF_ELEVATION: 12.0},
        unique_id="42.360_-71.060",
    )
    entry.add_to_hass(hass)
    MockConfigEntry(domain=DOMAIN, unique_id="51.500_-0.120").add_to_hass(hass)

    # Only the elevation changes: the location is still its own.
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    with patch("custom_components.iss_tracker.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _reconfigure_input(42.36, -71.06, 15)
        )
        await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_ELEVATION] == 15.0

    # Moving onto another location is refused.
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _reconfigure_input(51.5, -0.12)
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.unique_id == "42.360_-71.060"


async def test_options_flow(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_LATITUDE: 1, CONF_LONGITUDE: 2})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(result["flow_id"], OPTIONS)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        **OPTIONS,
        CONF_N2YO_API_KEY: "",
        CONF_SHOW_PANEL: True,
        CONF_SHOW_CALENDAR: True,
        CONF_UNITS: "auto",
    }


async def test_options_units(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_LATITUDE: 1, CONF_LONGITUDE: 2})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            result["flow_id"], {**OPTIONS, CONF_UNITS: "nautical"}
        )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**OPTIONS, CONF_UNITS: "metric"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_UNITS] == "metric"


async def test_options_peak_below_mask(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_LATITUDE: 1, CONF_LONGITUDE: 2})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**OPTIONS, CONF_MIN_ELEVATION: 30, CONF_MIN_PEAK_ELEVATION: 20}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_MIN_PEAK_ELEVATION: "peak_below_mask"}


async def test_options_n2yo_key_checked(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_LATITUDE: 1, CONF_LONGITUDE: 2})
    entry.add_to_hass(hass)

    aioclient_mock.get(re.compile(r"n2yo\.com.*apiKey=bad"), json={"error": "Invalid API Key!"})
    aioclient_mock.get(
        re.compile(r"n2yo\.com.*apiKey=good"),
        json={"info": {"satid": 25544}, "tle": f"{LINE1}\r\n{LINE2}"},
    )

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**OPTIONS, CONF_N2YO_API_KEY: "bad"}
    )
    assert result["errors"] == {CONF_N2YO_API_KEY: "invalid_n2yo_key"}

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**OPTIONS, CONF_N2YO_API_KEY: " good "}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_N2YO_API_KEY] == "good"
