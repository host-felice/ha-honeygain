"""Fork features: reauth, duplicates, new clients, Lucky Pot errors."""
import custom_components.honeygain  # noqa
from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from test_removed import DEV, fake_api

DATA = {"email": "bruce@example.com", "password": "old"}


async def setup(hass, api, **kw):
    entry = MockConfigEntry(domain="honeygain", data=DATA, **kw)
    entry.add_to_hass(hass)
    with patch("custom_components.honeygain.HoneyGain", return_value=api):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_rejected_password_asks_for_a_new_one(hass, login):
    login.return_value.status_code = 401
    entry = await setup(hass, fake_api())
    assert entry.state is ConfigEntryState.SETUP_ERROR
    [flow] = hass.config_entries.flow.async_progress()
    assert flow["context"]["source"] == "reauth"

    login.return_value.status_code = 200
    with patch("custom_components.honeygain.config_flow.HoneyGain") as hg, \
            patch("custom_components.honeygain.HoneyGain", return_value=fake_api()):
        hg.return_value.login.return_value = True
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], {"password": "new"})
        await hass.async_block_till_done()
    assert result["reason"] == "reauth_successful"
    assert entry.data["password"] == "new"
    assert entry.state is ConfigEntryState.LOADED


async def test_same_account_twice(hass):
    entry = await setup(hass, fake_api())
    assert entry.unique_id == "bruce@example.com"  # set on old entries at setup
    result = await hass.config_entries.flow.async_init(
        "honeygain", context={"source": SOURCE_USER},
        data={"email": "Bruce@Example.com", "password": "x"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_new_client_appears_without_restart(hass):
    api = fake_api()
    await setup(hass, api)
    assert hass.states.get("sensor.clark_total_credits") is None
    api.devices.return_value = [DEV, {**DEV, "id": "bbb", "title": "Clark"}]
    with patch("custom_components.honeygain.HoneyGain", return_value=api):
        data = next(iter(hass.data["honeygain"].values()))
        await hass.async_add_executor_job(lambda: data.update(no_throttle=True))
        await hass.async_block_till_done()
    assert hass.states.get("sensor.clark_total_credits").state == "1"


async def test_lucky_pot_not_opened_is_an_error(hass):
    api = fake_api()
    api.open_honeypot.return_value = {"success": False, "credits": None}
    await setup(hass, api)
    with pytest.raises(HomeAssistantError, match="already opened"):
        await hass.services.async_call(
            "button", "press", {"entity_id": "button.open_lucky_pot"}, blocking=True)
