import custom_components.honeygain  # noqa
from unittest.mock import MagicMock, patch

from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

D = "honeygain"
DEVICES = [
    {"id": "aaa", "ip": "::ffff:1.1.1.1", "title": "Bruce", "status": "active",
     "streaming_enabled": True, "stats": {"total_traffic": 0, "total_credits": 1, "streaming_seconds": 2}},
    # two clients behind the same IP: ambiguous, must not be migrated
    {"id": "bbb", "ip": "::ffff:2.2.2.2", "title": "Clark", "status": "active",
     "streaming_enabled": True, "stats": {"total_traffic": 0, "total_credits": 1, "streaming_seconds": 2}},
    {"id": "ccc", "ip": "::ffff:2.2.2.2", "title": "Diana", "status": "active",
     "streaming_enabled": True, "stats": {"total_traffic": 0, "total_credits": 1, "streaming_seconds": 2}},
]


def fake_api():
    api = MagicMock()
    api.devices.return_value = DEVICES
    api.me.return_value = {"referral_code": "ref", "active_devices_count": 3}
    api.balances.return_value = {"payout": {"usd_cents": 100}, "realtime": {"usd_cents": 5}}
    g = {"gathering": {"credits": 1, "bytes": 10}, "total": {"credits": 1},
         "referral": {"credits": 0}, "winning": {"credits": 0}}
    api.stats_today.return_value = g
    api.stats_today_jt.return_value = g
    return api


async def test_migration(hass):
    entry = MockConfigEntry(domain=D, data={"email": "a@b.c", "password": "x"})
    entry.add_to_hass(hass)
    devreg, entreg = dr.async_get(hass), er.async_get(hass)

    def old(ip, keys):
        dev = devreg.async_get_or_create(config_entry_id=entry.entry_id,
                                         identifiers={(D, f"{D}-{ip}")}, name="x")
        for k in keys:
            entreg.async_get_or_create("sensor", D, f"{D}-{ip}-{k}",
                                       config_entry=entry, device_id=dev.id)
        return dev

    current = old("::ffff:1.1.1.1", ["ip_address", "total_credits"])
    entreg.async_get_or_create("binary_sensor", D, f"{D}-::ffff:1.1.1.1-status",
                               config_entry=entry, device_id=current.id)
    stale = old("::ffff:9.9.9.9", ["ip_address"])
    shared = old("::ffff:2.2.2.2", ["ip_address"])
    ip_eid = entreg.async_get_entity_id("sensor", D, f"{D}-::ffff:1.1.1.1-ip_address")

    p = patch("custom_components.honeygain.HoneyGain", return_value=fake_api())
    p.start()
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # current device kept its HA device and entity ids, now keyed by the API id
    assert devreg.async_get(current.id).identifiers == {(D, f"{D}-aaa")}
    assert entreg.async_get(ip_eid).unique_id == f"{D}-aaa-ip_address"
    assert entreg.async_get(ip_eid).device_id == current.id
    assert entreg.async_get_entity_id("binary_sensor", D, f"{D}-aaa-status")
    assert len([e for e in er.async_entries_for_device(entreg, current.id)]) == 10
    # no duplicate device for aaa
    aaa = [d for d in dr.async_entries_for_config_entry(devreg, entry.entry_id)
           if (D, f"{D}-aaa") in d.identifiers]
    assert len(aaa) == 1
    # shared IP untouched, stale untouched
    assert devreg.async_get(shared.id).identifiers == {(D, f"{D}-::ffff:2.2.2.2")}
    assert devreg.async_get(stale.id).identifiers == {(D, f"{D}-::ffff:9.9.9.9")}

    # removal: stale/shared-old devices yes, live and account no
    from custom_components.honeygain import async_remove_config_entry_device as rm
    acct = devreg.async_get_device(identifiers={(D, f"{D}-ref")})
    assert await rm(hass, entry, devreg.async_get(stale.id))
    assert await rm(hass, entry, devreg.async_get(shared.id))
    assert not await rm(hass, entry, devreg.async_get(current.id))
    assert not await rm(hass, entry, acct)

    # second setup is a no-op

    assert entry.minor_version == 2

    # later the shared IP becomes unique: a reload must not migrate again
    DEVICES.pop()
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert devreg.async_get(shared.id).identifiers == {(D, f"{D}-::ffff:2.2.2.2")}
