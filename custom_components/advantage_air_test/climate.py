"""Climate platform for Advantage Air integration."""
from __future__ import annotations

import logging

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, PRECISION_WHOLE, TEMP_CELSIUS
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ADVANTAGE_AIR_STATE_CLOSE,
    ADVANTAGE_AIR_STATE_OFF,
    ADVANTAGE_AIR_STATE_ON,
    ADVANTAGE_AIR_STATE_OPEN,
    DOMAIN as ADVANTAGE_AIR_DOMAIN,
)
from .entity import AdvantageAirAcEntity, AdvantageAirZoneEntity

ADVANTAGE_AIR_HVAC_MODES = {
    "heat": HVACMode.HEAT,
    "cool": HVACMode.COOL,
    "vent": HVACMode.FAN_ONLY,
    "dry": HVACMode.DRY,
    "myauto": HVACMode.HEAT_COOL,
}
HASS_HVAC_MODES = {v: k for k, v in ADVANTAGE_AIR_HVAC_MODES.items()}

ADVANTAGE_AIR_FAN_MODES = {
    "autoAA": FAN_AUTO,
    "low": FAN_LOW,
    "medium": FAN_MEDIUM,
    "high": FAN_HIGH,
}
HASS_FAN_MODES = {v: k for k, v in ADVANTAGE_AIR_FAN_MODES.items()}
FAN_SPEEDS = {FAN_LOW: 30, FAN_MEDIUM: 60, FAN_HIGH: 100}

ADVANTAGE_AIR_AUTOFAN = "aaAutoFanModeEnabled"
ADVANTAGE_AIR_MYZONE = "MyZone"
ADVANTAGE_AIR_SERVICE_SET_MYZONE = "set_myzone"
ADVANTAGE_AIR_MYAUTO = "MyAuto"
ADVANTAGE_AIR_MYAUTO_ENABLED = "myAutoModeEnabled"
ADVANTAGE_AIR_MYTEMP = "MyTemp"
ADVANTAGE_AIR_MYTEMP_ENABLED = "climateControlModeEnabled"
ADVANTAGE_AIR_HEAT_TARGET = "myAutoHeatTargetTemp"
ADVANTAGE_AIR_COOL_TARGET = "myAutoCoolTargetTemp"

PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AdvantageAir climate platform."""

    instance = hass.data[ADVANTAGE_AIR_DOMAIN][config_entry.entry_id]

    entities: list[ClimateEntity] = []
    for ac_key, ac_device in instance["coordinator"].data["aircons"].items():
        entities.append(AdvantageAirAC(instance, ac_key))
        for zone_key, zone in ac_device["zones"].items():
            # Only add zone climate control when zone is in temperature control
            if zone["type"] != 0:
                entities.append(AdvantageAirZone(instance, ac_key, zone_key))
    async_add_entities(entities)


class AdvantageAirAC(AdvantageAirAcEntity, ClimateEntity):
    """AdvantageAir AC unit."""

    _attr_fan_modes = [FAN_LOW, FAN_MEDIUM, FAN_HIGH]
    _attr_temperature_unit = TEMP_CELSIUS
    _attr_target_temperature_step = PRECISION_WHOLE
    _attr_max_temp = 32
    _attr_min_temp = 16
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE
    )

    def __init__(self, instance, ac_key):
        """Initialize an AdvantageAir AC unit."""
        super().__init__(instance, ac_key)
        self._attr_unique_id = f'{self.coordinator.data["system"]["rid"]}-{ac_key}'

        self._attr_preset_modes = [ADVANTAGE_AIR_MYZONE]
        self._attr_supported_features = ClimateEntityFeature.FAN_MODE

        # Add "MyTemp" preset if available
        if ADVANTAGE_AIR_MYTEMP_ENABLED in self._ac:
            self._attr_preset_modes += [ADVANTAGE_AIR_MYTEMP]
            self._attr_supported_features |= ClimateEntityFeature.PRESET_MODE

        # Add "MyAuto" preset if available
        if ADVANTAGE_AIR_MYAUTO_ENABLED in self._ac:
            self._attr_preset_modes += [ADVANTAGE_AIR_MYAUTO]
            self._attr_supported_features |= ClimateEntityFeature.PRESET_MODE

    @property
    def target_temperature(self) -> float | None:
        """Return the current target temperature."""
        return self._ac["setTemp"]

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current HVAC modes."""
        if self._ac["state"] == ADVANTAGE_AIR_STATE_ON:
            return ADVANTAGE_AIR_HVAC_MODES[self._ac["mode"]]
        return HVACMode.OFF

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return the available HVAC modes."""
        # MyTemp only supports cooling and heating
        if self._ac.get(ADVANTAGE_AIR_MYTEMP_ENABLED):
            return [HVACMode.OFF, HVACMode.COOL, HVACMode.HEAT]
        # MyAuto adds support for Auto
        if self._ac.get(ADVANTAGE_AIR_MYAUTO_ENABLED):
            return [
                HVACMode.OFF,
                HVACMode.COOL,
                HVACMode.HEAT,
                HVACMode.FAN_ONLY,
                HVACMode.DRY,
                HVACMode.HEAT_COOL,
            ]
        # MyZone does not support auto
        return [
            HVACMode.OFF,
            HVACMode.COOL,
            HVACMode.HEAT,
            HVACMode.FAN_ONLY,
            HVACMode.DRY,
        ]

    @property
    def fan_mode(self) -> str | None:
        """Return the current fan modes."""
        return ADVANTAGE_AIR_FAN_MODES.get(self._ac["fan"])

    @property
    def fan_modes(self) -> list[str] | None:
        """Return the list of available fan modes."""
        # Auto is only available when AutoFan is enabled
        if self._ac.get(ADVANTAGE_AIR_AUTOFAN):
            return self._attr_fan_modes + [FAN_AUTO]
        return self._attr_fan_modes

    @property
    def preset_mode(self) -> str:
        """Return the current preset mode."""
        if self._ac.get(ADVANTAGE_AIR_MYAUTO_ENABLED):
            return ADVANTAGE_AIR_MYAUTO
        if self._ac.get(ADVANTAGE_AIR_MYTEMP_ENABLED):
            return ADVANTAGE_AIR_MYTEMP
        return ADVANTAGE_AIR_MYZONE

    @property
    def supported_features(self) -> int:
        """Return the list of supported features."""
        # MyTemp does not support setting a temperature of any kind
        if self.preset_mode == ADVANTAGE_AIR_MYTEMP:
            return self._attr_supported_features

        # MyAuto in Heat/Cool supports setting a temperature range
        if self.hvac_mode == HVACMode.HEAT_COOL:
            return (
                self._attr_supported_features
                | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
            )

        # MyAuto and MyZone in any other mode supports a setting a target temperature
        return self._attr_supported_features | ClimateEntityFeature.TARGET_TEMPERATURE

    @property
    def target_temperature_high(self) -> float | None:
        """Return the temperature cool mode is enabled."""
        return self._ac.get(ADVANTAGE_AIR_COOL_TARGET, 24)

    @property
    def target_temperature_low(self) -> float | None:
        """Return the temperature heat mode is enabled."""
        return self._ac.get(ADVANTAGE_AIR_HEAT_TARGET, 20)

    async def async_set_hvac_mode(self, hvac_mode) -> None:
        """Set the HVAC Mode and State."""
        if hvac_mode == HVACMode.OFF:
            await self.async_change(
                {self.ac_key: {"info": {"state": ADVANTAGE_AIR_STATE_OFF}}}
            )
        else:
            await self.async_change(
                {
                    self.ac_key: {
                        "info": {
                            "state": ADVANTAGE_AIR_STATE_ON,
                            "mode": HASS_HVAC_MODES.get(hvac_mode),
                        }
                    }
                }
            )

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set the Fan Mode."""
        await self.async_change(
            {self.ac_key: {"info": {"fan": HASS_FAN_MODES.get(fan_mode)}}}
        )

    async def async_set_temperature(self, **kwargs) -> None:
        """Set the Temperature."""
        if ATTR_TEMPERATURE in kwargs:
            await self.async_change(
                {self.ac_key: {"info": {"setTemp": kwargs[ATTR_TEMPERATURE]}}}
            )
        if ATTR_TARGET_TEMP_LOW in kwargs and ATTR_TARGET_TEMP_HIGH in kwargs:
            await self.async_change(
                {
                    self.ac_key: {
                        "info": {
                            ADVANTAGE_AIR_COOL_TARGET: kwargs[ATTR_TARGET_TEMP_HIGH],
                            ADVANTAGE_AIR_HEAT_TARGET: kwargs[ATTR_TARGET_TEMP_LOW],
                        }
                    }
                }
            )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the preset mode."""
        change = {}
        if ADVANTAGE_AIR_MYTEMP_ENABLED in self._ac:
            change[ADVANTAGE_AIR_MYTEMP_ENABLED] = preset_mode == ADVANTAGE_AIR_MYTEMP
        if ADVANTAGE_AIR_MYAUTO_ENABLED in self._ac:
            change[ADVANTAGE_AIR_MYAUTO_ENABLED] = preset_mode == ADVANTAGE_AIR_MYAUTO
        await self.async_change({self.ac_key: {"info": change}})


class AdvantageAirZone(AdvantageAirZoneEntity, ClimateEntity):
    """AdvantageAir Zone control."""

    _attr_temperature_unit = TEMP_CELSIUS
    _attr_target_temperature_step = PRECISION_WHOLE
    _attr_max_temp = 32
    _attr_min_temp = 16
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT_COOL]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_temperature_unit = TEMP_CELSIUS
    _attr_target_temperature_step = PRECISION_WHOLE
    _attr_max_temp = 32
    _attr_min_temp = 16

    def __init__(self, instance, ac_key, zone_key) -> None:
        """Initialize an AdvantageAir Zone control."""
        super().__init__(instance, ac_key, zone_key)
        self._attr_name = self._zone["name"]
        self._attr_unique_id = (
            f'{self.coordinator.data["system"]["rid"]}-{ac_key}-{zone_key}'
        )

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current state as HVAC mode."""
        if self._zone["state"] == ADVANTAGE_AIR_STATE_OPEN:
            return HVACMode.HEAT_COOL
        return HVACMode.OFF

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self._zone["measuredTemp"]

    @property
    def target_temperature(self) -> float:
        """Return the target temperature."""
        return self._zone["setTemp"]

    async def async_set_hvac_mode(self, hvac_mode: str) -> None:
        """Set the HVAC Mode and State."""
        await self.async_change(
            {
                self.ac_key: {
                    "zones": {
                        self.zone_key: {
                            "state": ADVANTAGE_AIR_STATE_OPEN
                            if hvac_mode == HVACMode.OFF
                            else ADVANTAGE_AIR_STATE_CLOSE
                        }
                    }
                }
            }
        )

    async def async_set_temperature(self, **kwargs) -> None:
        """Set the Temperature."""
        temp = kwargs.get(ATTR_TEMPERATURE)
        await self.async_change(
            {self.ac_key: {"zones": {self.zone_key: {"setTemp": temp}}}}
        )
