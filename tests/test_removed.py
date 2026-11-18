import custom_components.honeygain  # noqa
from unittest.mock import MagicMock, patch

from homeassistant.helpers.entity_component import async_update_entity
from pytest_homeassistant_custom_component.common import MockConfigEntry

DEV = {"id": "aaa", "ip": "1.1.1.1", "title": "Bruce", "status": "active",
       "streaming_enabled": True,
       "stats": {"total_traffic": 0, "total_credits": 1, "streaming_seconds": 2}}


def fake_api():
    api = MagicMock()
    api.devices.return_value = [DEV]
    api.me.return_value = {"referral_code": "ref", "active_devices_count": 1}
    api.balances.return_value = {"payout": {"usd_cents": 100}, "realtime": {"usd_cents": 5}}
    g = {"gathering": {"credits": 1, "bytes": 10}, "total": {"credits": 1},
         "referral": {"credits": 0}, "winning": {"credits": 0}}
    api.stats_today.return_value = g
    return api


async def test_removed_device(hass):
    entry = MockConfigEntry(domain="honeygain", data={"email": "a@b.c", "password": "x"})
    entry.add_to_hass(hass)
    with patch("custom_components.honeygain.HoneyGain", return_value=fake_api()):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    sensor, binary = "sensor.bruce_total_credits", "binary_sensor.bruce_status"
    assert hass.states.get(sensor).state == "1"

    # the client is removed from the Honeygain account
    hass.data["honeygain"][entry.entry_id].devices = []
    with patch("custom_components.honeygain.HoneygainData.update"):
        for _ in range(2):
            await async_update_entity(hass, sensor)
            await async_update_entity(hass, binary)
    assert hass.states.get(sensor).state == "unavailable"
    assert hass.states.get(binary).state == "unavailable"

    # it comes back
    hass.data["honeygain"][entry.entry_id].devices = [DEV]
    with patch("custom_components.honeygain.HoneygainData.update"):
        await async_update_entity(hass, sensor)
    assert hass.states.get(sensor).state == "1"


async def test_jmpt_entities_removed(hass):
    from homeassistant.helpers import entity_registry as er
    entry = MockConfigEntry(domain="honeygain", data={"email": "a@b.c", "password": "x"})
    entry.add_to_hass(hass)
    entreg = er.async_get(hass)
    jt = entreg.async_get_or_create("sensor", "honeygain", "honeygain-ref-today_credits_jt",
                                    config_entry=entry)
    with patch("custom_components.honeygain.HoneyGain", return_value=fake_api()):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entreg.async_get(jt.entity_id) is None
    assert entreg.async_get_entity_id("sensor", "honeygain", "honeygain-ref-today_credits")
