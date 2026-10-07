# iCal Export for Home Assistant

[![Validate](https://github.com/jakubkosinski/ha-calendar/actions/workflows/validate.yml/badge.svg)](https://github.com/jakubkosinski/ha-calendar/actions/workflows/validate.yml)
[![Tests](https://github.com/jakubkosinski/ha-calendar/actions/workflows/tests.yml/badge.svg)](https://github.com/jakubkosinski/ha-calendar/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Publishes selected Home Assistant `calendar.*` entities as iCal (`.ics`) feeds you can subscribe to in Apple Calendar (macOS and iOS).

Apple Calendar can't send HA's `Authorization: Bearer` header, so feeds are protected by a long random **secret token in the URL** instead.

## Install

**HACS:** [![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jakubkosinski&repository=ha-calendar&category=integration) or add this repository manually as a custom repository (category *Integration*), install, restart HA.
**Manual:** copy `custom_components/ical_export` into your HA `config/custom_components/`.

## Configure

*Settings → Devices & services → Add integration → iCal Export.* Pick a feed name and the calendars to include. You can add several feeds. Under *Configure* you can change the calendars and the time window (default: 30 days back, 365 ahead).

A persistent notification lists the URLs:

- `/api/ical_export/<token>/all.ics` – all selected calendars combined
- `/api/ical_export/<token>/<calendar_object_id>.ics` – a single calendar

Each is shown as `https://` and `webcal://`.

## Subscribe in Apple Calendar

- **macOS:** File → New Calendar Subscription → paste URL.
- **iOS:** Settings → Calendar → Accounts → Add Account → Other → Add Subscribed Calendar.

Your HA must be reachable from the device (Nabu Casa, reverse proxy with HTTPS, or VPN). Apple refuses plain http on some versions for remote hosts, so prefer HTTPS.

## Security

Anyone with the URL can read the calendar. Treat it like a password. Press the **Regenerate token** button on the device to invalidate old URLs; the notification is re-issued with new ones.

## Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt
pytest && ruff check .
docker compose -f dev/docker-compose.yml up   # HA on :8123 with demo calendars
```

---

# iCal Export (PL)

Integracja udostępnia wybrane kalendarze HA jako feedy iCal do subskrypcji w Apple Calendar. Zabezpieczenie: sekretny token w URL (rotacja przyciskiem „Wygeneruj nowy token”). Instalacja przez HACS lub ręczne skopiowanie `custom_components/ical_export`; konfiguracja w *Ustawienia → Urządzenia i usługi*. Adresy URL (`https://` i `webcal://`) pojawią się w powiadomieniu. HA musi być dostępny z internetu (Nabu Casa / reverse proxy z HTTPS) lub przez VPN.
