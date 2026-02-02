"""Aquanta water heater component."""

from __future__ import annotations

from homeassistant.components.water_heater import (
    STATE_ECO,
    STATE_PERFORMANCE,
    STATE_OFF,
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import AquantaEntity
from .const import DOMAIN, LOGGER


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Initialize Aquanta devices from config entry."""

    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    entities: list[AquantaWaterHeater] = []

    for aquanta_id in coordinator.data["devices"]:
        entities.append(
            AquantaWaterHeater(coordinator, aquanta_id)
        )

    async_add_entities(entities)

class AquantaWaterHeater(AquantaEntity, WaterHeaterEntity):
    """Representation of an Aquanta water heater controller."""

    _attr_has_entity_name = True
    _attr_supported_features = (WaterHeaterEntityFeature.AWAY_MODE | WaterHeaterEntityFeature.TARGET_TEMPERATURE)
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_operation_list = [STATE_ECO, STATE_PERFORMANCE, STATE_OFF]
    _attr_name = "Water heater"

    def __init__(self, coordinator, aquanta_id) -> None:
        """Initialize the water heater."""
        super().__init__(coordinator, aquanta_id)
        self._attr_name = "Water heater"
        self._attr_unique_id = self._base_unique_id + "_water_heater"
        LOGGER.debug("Created water heater with unique ID %s", self._attr_unique_id)

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self.coordinator.data["devices"][self.aquanta_id]["water"]["temperature"]

    @property
    def current_operation(self):
        """Return current operation ie. eco, performance, off."""
        operation = STATE_OFF

        if (
            self.coordinator.data["devices"][self.aquanta_id]["info"]["currentMode"][
                "type"
            ]
            != "off"
        ):
            found = False

            for record in self.coordinator.data["devices"][self.aquanta_id]["info"][
                "records"
            ]:
                if record["type"] == "boost" and record["state"] == "ongoing":
                    operation = STATE_PERFORMANCE
                    found = True
                elif record["type"] == "away" and record["state"] == "ongoing":
                    operation = STATE_OFF
                    found = True
                    break

            if not found:
                operation = STATE_ECO

        return operation

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        if self.coordinator.data["devices"][self.aquanta_id]["advanced"][
            "thermostatEnabled"
        ]:
            return self.coordinator.data["devices"][self.aquanta_id]["advanced"][
                "setPoint"
            ]
        else:
            return None

#    @property
#    def min_temp(self):
#        """Return the minimum temperature."""
#        return 110  # Fahrenheit (Aquanta standard min)

#    @property
#    def max_temp(self):
#        """Return the maximum temperature."""
#        return 140  # Fahrenheit (Aquanta standard max)

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        import aiohttp # Import locally to avoid top-level dependency issues

        target_temperature = kwargs.get("temperature")
        if target_temperature is None:
            return

        # 1. Build the URL
        url = f"https://portal.aquanta.io/api/v1/devices/{self.aquanta_id}/setpoint"

        # 2. Get the auth headers from the existing connection
        # The coordinator usually holds the 'api' object or 'device' session
        # We try to grab the headers from the device session directly
        try:
            headers = self._device._session.headers
        except AttributeError:
            # Fallback if _device isn't directly accessible, try coordinator
            headers = self.coordinator.api._session.headers

        # 3. Send the command manually
        async with aiohttp.ClientSession() as session:
            payload = {"temperature": target_temperature}
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    # Update local data so the UI slider doesn't bounce back
                    self.coordinator.data["devices"][self.aquanta_id]["advanced"]["setPoint"] = target_temperature
                    self.async_write_ha_state()
                    
                    # Force a refresh from the cloud
                    await self.coordinator.async_request_refresh()
                else:
                    # Log error if it fails
                    LOGGER.error("Failed to set Aquanta temperature: %s", await response.text())
