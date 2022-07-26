"""Light platform for Advantage Air integration."""
from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ADVANTAGE_AIR_STATE_OFF,
    ADVANTAGE_AIR_STATE_ON,
    DOMAIN as ADVANTAGE_AIR_DOMAIN,
)
from .entity import AdvantageAirThingEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AdvantageAir light platform."""

    instance = hass.data[ADVANTAGE_AIR_DOMAIN][config_entry.entry_id]

    entities: list[LightEntity] = []
    if "myLights" in instance["coordinator"].data:
        for light in instance["coordinator"].data["myLights"]["lights"].values():
            if light.get("relay"):
                entities.append(AdvantageAirLight(instance, light))
            else:
                entities.append(AdvantageAirLightDimmable(instance, light))
    if "myThings" in instance["coordinator"].data:
        for thing in instance["coordinator"].data["myThings"]["things"].values():
            if thing["channelDipState"] == 4:  # 4 = "Light (on/off)""
                entities.append(AdvantageAirThingLight(instance, thing))
            elif thing["channelDipState"] == 5:  # 5 = "Light (Dimmable)""
                entities.append(AdvantageAirThingLightDimmable(instance, thing))
    async_add_entities(entities)


class AdvantageAirLight(AdvantageAirThingEntity, LightEntity):
    """Representation of Advantage Air Light controlled by MyLights."""

    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(self, instance, light):
        """Initialize an Advantage Air Light."""
        super().__init__(instance, light)
        self.async_change = instance["lights"]

    @property
    def _data(self):
        """Return the light object."""
        return self.coordinator.data["myLights"]["lights"][self._id]

    @property
    def is_on(self) -> bool:
        """Return if the light is on."""
        return self._data["state"] == ADVANTAGE_AIR_STATE_ON

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        await self.async_change({"id": self._id, "state": ADVANTAGE_AIR_STATE_ON})

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        await self.async_change({"id": self._id, "state": ADVANTAGE_AIR_STATE_OFF})


class AdvantageAirLightDimmable(AdvantageAirLight):
    """Representation of Advantage Air Dimmable Light controlled by MyLights."""

    _attr_supported_color_modes = {ColorMode.ONOFF, ColorMode.BRIGHTNESS}

    @property
    def brightness(self) -> int:
        """Return the brightness of this light between 0..255."""
        return round(self._data["value"] * 255 / 100)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on and optionally set the brightness."""
        data = {"id": self._id, "state": ADVANTAGE_AIR_STATE_ON}
        if ATTR_BRIGHTNESS in kwargs:
            data["value"] = round(kwargs[ATTR_BRIGHTNESS] * 100 / 255)
        await self.async_change(data)


class AdvantageAirThingLight(AdvantageAirThingEntity, LightEntity):
    """Representation of Advantage Air Light controlled by myThings."""

    _attr_supported_color_modes = {ColorMode.ONOFF}


class AdvantageAirThingLightDimmable(AdvantageAirThingEntity, LightEntity):
    """Representation of Advantage Air Dimmable Light controlled by myThings."""

    _attr_supported_color_modes = {ColorMode.ONOFF, ColorMode.BRIGHTNESS}

    @property
    def brightness(self) -> int:
        """Return the brightness of this light between 0..255."""
        return round(self._data["value"] * 255 / 100)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on by setting the brightness."""
        await self.async_change(
            {
                "id": self._id,
                "value": round(kwargs.get(ATTR_BRIGHTNESS, 255) * 100 / 255),
            }
        )
