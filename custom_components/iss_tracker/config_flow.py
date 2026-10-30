"""Config flow for ISS Tracker."""

from __future__ import annotations

import math
from typing import Any

from homeassistant.config_entries import (
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import (
    CONF_ELEVATION,
    CONF_LATITUDE,
    CONF_LOCATION,
    CONF_LONGITUDE,
    CONF_NAME,
    DEGREE,
    UnitOfLength,
    UnitOfTime,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    LocationSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
import voluptuous as vol

from . import IssConfigEntry
from .const import (
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
    DEFAULT_ALERT_LEAD_MINUTES,
    DEFAULT_FORECAST_DAYS,
    DEFAULT_MAX_SUN_ELEVATION,
    DEFAULT_MIN_ELEVATION,
    DEFAULT_MIN_PEAK_ELEVATION,
    DEFAULT_MIN_VISIBLE_DURATION,
    DEFAULT_SHOW_CALENDAR,
    DEFAULT_SHOW_PANEL,
    DEFAULT_UNITS,
    DOMAIN,
    UNITS,
    USER_AGENT,
)
from .elements import ElementsError, SourceRejectedError, fetch_n2yo

DEFAULT_NAME = "Home"


def _number(minimum: float, maximum: float, step: float, unit: str | None = None) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=step,
            unit_of_measurement=unit,
            mode=NumberSelectorMode.BOX,
        )
    )


def _coordinates(location: dict[str, Any]) -> tuple[float, float] | None:
    """Latitude and longitude from the location selector, or None when out of range.

    Before Home Assistant 2026.11 the selector accepts any number; from
    2026.11 it refuses coordinates out of range before the flow sees them.
    Longitudes written 0-360 (or wrapped further) are brought into -180..180
    so that the same place is recognised as a duplicate whichever way it was
    typed.
    """
    latitude = round(float(location[CONF_LATITUDE]), 5)
    longitude = round(float(location[CONF_LONGITUDE]), 5)
    if abs(longitude) > 180:
        longitude = round((longitude + 180) % 360 - 180, 5)
    # Written so that NaN fails too.
    if not (math.isfinite(longitude) and -90 <= latitude <= 90):
        return None
    return latitude, longitude


def _unique_id(latitude: float, longitude: float) -> str:
    return f"{latitude:.3f}_{longitude:.3f}"


def _elevation_selector() -> NumberSelector:
    return _number(-500, 9000, 1, UnitOfLength.METERS)


class IssTrackerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add an observing location."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pick the location to predict passes for."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if (coordinates := _coordinates(user_input[CONF_LOCATION])) is None:
                errors[CONF_LOCATION] = "invalid_location"
            else:
                latitude, longitude = coordinates
                await self.async_set_unique_id(_unique_id(latitude, longitude))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={
                        CONF_LATITUDE: latitude,
                        CONF_LONGITUDE: longitude,
                        CONF_ELEVATION: float(user_input[CONF_ELEVATION]),
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(
                    CONF_LOCATION,
                    default={
                        CONF_LATITUDE: self.hass.config.latitude,
                        CONF_LONGITUDE: self.hass.config.longitude,
                    },
                ): LocationSelector(),
                vol.Required(CONF_ELEVATION, default=self.hass.config.elevation): (
                    _elevation_selector()
                ),
            }
        )
        if user_input is not None:
            # Keep what was typed, so only the location needs correcting.
            schema = self.add_suggested_values_to_schema(schema, user_input)
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Move a location in place, so the dashboard cards that show it keep working."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            if (coordinates := _coordinates(user_input[CONF_LOCATION])) is None:
                errors[CONF_LOCATION] = "invalid_location"
            else:
                latitude, longitude = coordinates
                unique_id = _unique_id(latitude, longitude)
                if unique_id != entry.unique_id:
                    await self.async_set_unique_id(unique_id, raise_on_progress=False)
                    self._abort_if_unique_id_configured()
                changed = self.hass.config_entries.async_update_entry(
                    entry,
                    unique_id=unique_id,
                    data={
                        **entry.data,
                        CONF_LATITUDE: latitude,
                        CONF_LONGITUDE: longitude,
                        CONF_ELEVATION: float(user_input[CONF_ELEVATION]),
                    },
                )
                # A loaded entry reloads through its update listener; one that
                # is not loaded (still retrying setup, say) is retried now.
                if changed and entry.state is not ConfigEntryState.LOADED:
                    self.hass.config_entries.async_schedule_reload(entry.entry_id)
                return self.async_abort(reason="reconfigure_successful")

        schema = vol.Schema(
            {
                vol.Required(CONF_LOCATION): LocationSelector(),
                vol.Required(CONF_ELEVATION): _elevation_selector(),
            }
        )
        current = {
            CONF_LOCATION: {
                CONF_LATITUDE: entry.data[CONF_LATITUDE],
                CONF_LONGITUDE: entry.data[CONF_LONGITUDE],
            },
            CONF_ELEVATION: entry.data.get(CONF_ELEVATION, 0.0),
        }
        schema = self.add_suggested_values_to_schema(schema, user_input or current)
        return self.async_show_form(step_id="reconfigure", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: IssConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return IssTrackerOptionsFlow()


class IssTrackerOptionsFlow(OptionsFlow):
    """Tune which passes are reported."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}
        if user_input is not None:
            key = (user_input.get(CONF_N2YO_API_KEY) or "").strip()
            user_input[CONF_N2YO_API_KEY] = key
            if key and key != self.config_entry.options.get(CONF_N2YO_API_KEY):
                try:
                    await fetch_n2yo(
                        async_get_clientsession(self.hass), {"User-Agent": USER_AGENT}, key
                    )
                except SourceRejectedError:
                    errors[CONF_N2YO_API_KEY] = "invalid_n2yo_key"
                except ElementsError:
                    errors[CONF_N2YO_API_KEY] = "n2yo_unreachable"
            if user_input[CONF_MIN_PEAK_ELEVATION] < user_input[CONF_MIN_ELEVATION]:
                errors[CONF_MIN_PEAK_ELEVATION] = "peak_below_mask"
            if not errors:
                return self.async_create_entry(data=user_input)

        current = {**self.config_entry.options, **(user_input or {})}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_MIN_ELEVATION,
                    default=current.get(CONF_MIN_ELEVATION, DEFAULT_MIN_ELEVATION),
                ): _number(0, 45, 1, DEGREE),
                vol.Required(
                    CONF_MIN_PEAK_ELEVATION,
                    default=current.get(CONF_MIN_PEAK_ELEVATION, DEFAULT_MIN_PEAK_ELEVATION),
                ): _number(0, 90, 1, DEGREE),
                vol.Required(
                    CONF_MAX_SUN_ELEVATION,
                    default=current.get(CONF_MAX_SUN_ELEVATION, DEFAULT_MAX_SUN_ELEVATION),
                ): _number(-18, 0, 0.5, DEGREE),
                vol.Required(
                    CONF_MIN_VISIBLE_DURATION,
                    default=current.get(CONF_MIN_VISIBLE_DURATION, DEFAULT_MIN_VISIBLE_DURATION),
                ): _number(0, 600, 10, UnitOfTime.SECONDS),
                vol.Required(
                    CONF_FORECAST_DAYS,
                    default=current.get(CONF_FORECAST_DAYS, DEFAULT_FORECAST_DAYS),
                ): _number(1, 30, 1, UnitOfTime.DAYS),
                vol.Required(
                    CONF_ALERT_LEAD_MINUTES,
                    default=current.get(CONF_ALERT_LEAD_MINUTES, DEFAULT_ALERT_LEAD_MINUTES),
                ): _number(1, 240, 1, UnitOfTime.MINUTES),
                vol.Required(
                    CONF_SHOW_PANEL,
                    default=current.get(CONF_SHOW_PANEL, DEFAULT_SHOW_PANEL),
                ): BooleanSelector(),
                vol.Required(
                    CONF_SHOW_CALENDAR,
                    default=current.get(CONF_SHOW_CALENDAR, DEFAULT_SHOW_CALENDAR),
                ): BooleanSelector(),
                vol.Required(
                    CONF_UNITS,
                    default=current.get(CONF_UNITS, DEFAULT_UNITS),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=list(UNITS),
                        translation_key=CONF_UNITS,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_N2YO_API_KEY,
                    description={"suggested_value": current.get(CONF_N2YO_API_KEY, "")},
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
