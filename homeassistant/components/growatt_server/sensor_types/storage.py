"""Growatt Sensor definitions for the Storage type."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    ELECTRIC_CURRENT_AMPERE,
    ELECTRIC_POTENTIAL_VOLT,
    ENERGY_KILO_WATT_HOUR,
    FREQUENCY_HERTZ,
    PERCENTAGE,
    POWER_WATT,
)

from .sensor_entity_description import GrowattSensorEntityDescription

STORAGE_SENSOR_TYPES: tuple[GrowattSensorEntityDescription, ...] = (
    GrowattSensorEntityDescription(
        key="storage_storage_production_today",
        name="Storage production today",
        api_key="eBatDisChargeToday",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
    ),
    GrowattSensorEntityDescription(
        key="storage_storage_production_lifetime",
        name="Lifetime Storage production",
        api_key="eBatDisChargeTotal",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
    ),
    GrowattSensorEntityDescription(
        key="storage_grid_discharge_today",
        name="Grid discharged today",
        api_key="eacDisChargeToday",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
    ),
    GrowattSensorEntityDescription(
        key="storage_load_consumption_today",
        name="Load consumption today",
        api_key="eopDischrToday",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
    ),
    GrowattSensorEntityDescription(
        key="storage_load_consumption_lifetime",
        name="Lifetime load consumption",
        api_key="eopDischrTotal",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
    ),
    GrowattSensorEntityDescription(
        key="storage_grid_charged_today",
        name="Grid charged today",
        api_key="eacChargeToday",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
    ),
    GrowattSensorEntityDescription(
        key="storage_charge_storage_lifetime",
        name="Lifetime storaged charged",
        api_key="eChargeTotal",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
    ),
    GrowattSensorEntityDescription(
        key="storage_solar_production",
        name="Solar power production",
        api_key="ppv",
        native_unit_of_measurement=POWER_WATT,
        device_class=SensorDeviceClass.POWER,
    ),
    GrowattSensorEntityDescription(
        key="storage_battery_percentage",
        name="Battery percentage",
        api_key="capacity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
    ),
    GrowattSensorEntityDescription(
        key="storage_power_flow",
        name="Storage charging/ discharging(-ve)",
        api_key="pCharge",
        native_unit_of_measurement=POWER_WATT,
        device_class=SensorDeviceClass.POWER,
    ),
    GrowattSensorEntityDescription(
        key="storage_load_consumption_solar_storage",
        name="Load consumption(Solar + Storage)",
        api_key="rateVA",
        native_unit_of_measurement="VA",
    ),
    GrowattSensorEntityDescription(
        key="storage_charge_today",
        name="Charge today",
        api_key="eChargeToday",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
    ),
    GrowattSensorEntityDescription(
        key="storage_import_from_grid",
        name="Import from grid",
        api_key="pAcInPut",
        native_unit_of_measurement=POWER_WATT,
        device_class=SensorDeviceClass.POWER,
    ),
    GrowattSensorEntityDescription(
        key="storage_import_from_grid_today",
        name="Import from grid today",
        api_key="eToUserToday",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
    ),
    GrowattSensorEntityDescription(
        key="storage_import_from_grid_total",
        name="Import from grid total",
        api_key="eToUserTotal",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
    ),
    GrowattSensorEntityDescription(
        key="storage_load_consumption",
        name="Load consumption",
        api_key="outPutPower",
        native_unit_of_measurement=POWER_WATT,
        device_class=SensorDeviceClass.POWER,
    ),
    GrowattSensorEntityDescription(
        key="storage_grid_voltage",
        name="AC input voltage",
        api_key="vGrid",
        native_unit_of_measurement=ELECTRIC_POTENTIAL_VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        precision=2,
    ),
    GrowattSensorEntityDescription(
        key="storage_pv_charging_voltage",
        name="PV charging voltage",
        api_key="vpv",
        native_unit_of_measurement=ELECTRIC_POTENTIAL_VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        precision=2,
    ),
    GrowattSensorEntityDescription(
        key="storage_ac_input_frequency_out",
        name="AC input frequency",
        api_key="freqOutPut",
        native_unit_of_measurement=FREQUENCY_HERTZ,
        precision=2,
    ),
    GrowattSensorEntityDescription(
        key="storage_output_voltage",
        name="Output voltage",
        api_key="outPutVolt",
        native_unit_of_measurement=ELECTRIC_POTENTIAL_VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        precision=2,
    ),
    GrowattSensorEntityDescription(
        key="storage_ac_output_frequency",
        name="Ac output frequency",
        api_key="freqGrid",
        native_unit_of_measurement=FREQUENCY_HERTZ,
        precision=2,
    ),
    GrowattSensorEntityDescription(
        key="storage_current_PV",
        name="Solar charge current",
        api_key="iAcCharge",
        native_unit_of_measurement=ELECTRIC_CURRENT_AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        precision=2,
    ),
    GrowattSensorEntityDescription(
        key="storage_current_1",
        name="Solar current to storage",
        api_key="iChargePV1",
        native_unit_of_measurement=ELECTRIC_CURRENT_AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        precision=2,
    ),
    GrowattSensorEntityDescription(
        key="storage_grid_amperage_input",
        name="Grid charge current",
        api_key="chgCurr",
        native_unit_of_measurement=ELECTRIC_CURRENT_AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        precision=2,
    ),
    GrowattSensorEntityDescription(
        key="storage_grid_out_current",
        name="Grid out current",
        api_key="outPutCurrent",
        native_unit_of_measurement=ELECTRIC_CURRENT_AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        precision=2,
    ),
    GrowattSensorEntityDescription(
        key="storage_battery_voltage",
        name="Battery voltage",
        api_key="vBat",
        native_unit_of_measurement=ELECTRIC_POTENTIAL_VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        precision=2,
    ),
    GrowattSensorEntityDescription(
        key="storage_load_percentage",
        name="Load percentage",
        api_key="loadPercent",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        precision=2,
    ),
)