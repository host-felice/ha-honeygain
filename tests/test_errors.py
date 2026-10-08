import custom_components.honeygain  # noqa
import logging
from unittest.mock import MagicMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers.entity_component import async_update_entity
from pytest_homeassistant_custom_component.common import MockConfigEntry
from requests import ConnectionError

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
    api.stats_today_jt.return_value = g
    return api


def entry_for(hass):
    entry = MockConfigEntry(domain="honeygain", data={"email": "a@b.c", "password": "x"})
    entry.add_to_hass(hass)
    return entry


async def test_offline_at_startup_retries(hass):
    api = fake_api()
    api.login.side_effect = ConnectionError("down")
    entry = entry_for(hass)
    with patch("custom_components.honeygain.HoneyGain", return_value=api):
        await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_http_error_at_startup_retries(hass, caplog):
    api = fake_api()
    api.me.return_value = False
    api.balances.return_value = {}
    entry = entry_for(hass)
    with patch("custom_components.honeygain.HoneyGain", return_value=api):
        await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert "Honeygain update failed (balances, user)" in caplog.text


async def test_outage_after_setup(hass, caplog):
    api = fake_api()
    entry = entry_for(hass)
    with patch("custom_components.honeygain.HoneyGain", return_value=api):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    data = hass.data["honeygain"][entry.entry_id]
    ents = ["sensor.account_account_balance", "sensor.bruce_total_credits",
            "binary_sensor.bruce_status"]

    async def poll():
        await hass.async_add_executor_job(lambda: data.update(no_throttle=True))
        for e in ents:
            await async_update_entity(hass, e)

    await poll()
    assert hass.states.get(ents[0]).state == "1.00"

    caplog.clear()
    api.balances.side_effect = ConnectionError("down")
    for _ in range(3):
        await poll()
    for e in ents:
        assert hass.states.get(e).state == "unavailable", e
    msgs = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(msgs) == 1, [r.getMessage() for r in msgs]
    assert api.set_api_version.call_args.kwargs["version"] == "/v1"

    api.balances.side_effect = None
    api.balances.return_value = {"payout": {"usd_cents": 250}, "realtime": {"usd_cents": 5}}
    await poll()
    assert hass.states.get(ents[0]).state == "2.50"
    assert hass.states.get(ents[2]).state == "on"


async def test_bad_answers_after_setup(hass):
    api = fake_api()
    entry = entry_for(hass)
    with patch("custom_components.honeygain.HoneyGain", return_value=api):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    data = hass.data["honeygain"][entry.entry_id]
    api.devices.return_value = None
    data.update(no_throttle=True)
    assert not data.available and data.devices == [DEV]
    api.devices.return_value = [DEV]
    api.me.side_effect = AttributeError("'NoneType' object has no attribute 'get'")
    data.update(no_throttle=True)
    assert not data.available
    await async_update_entity(hass, "button.open_lucky_pot")
    assert hass.states.get("button.open_lucky_pot").state == "unavailable"


async def test_login_without_token_retries(hass):
    api = fake_api()
    api.login.side_effect = KeyError("data")
    entry = entry_for(hass)
    with patch("custom_components.honeygain.HoneyGain", return_value=api):
        await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
