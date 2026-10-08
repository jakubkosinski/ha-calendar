# iCal Export for Home Assistant

[![Validate](https://github.com/jakubkosinski/homeassistant-ical-export/actions/workflows/validate.yml/badge.svg)](https://github.com/jakubkosinski/homeassistant-ical-export/actions/workflows/validate.yml)
[![Tests](https://github.com/jakubkosinski/homeassistant-ical-export/actions/workflows/tests.yml/badge.svg)](https://github.com/jakubkosinski/homeassistant-ical-export/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Publishes selected Home Assistant `calendar.*` entities as iCal (`.ics`) feeds you can subscribe to in Apple Calendar (macOS and iOS).

Apple Calendar can't send HA's `Authorization: Bearer` header, so feeds are protected by a long random **secret token in the URL** instead.

## Install

**HACS:** [![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jakubkosinski&repository=homeassistant-ical-export&category=integration) or add this repository manually as a custom repository (category *Integration*), install, restart HA.
**Manual:** copy `custom_components/ical_export` into your HA `config/custom_components/`.

## Configure

*Settings → Devices & services → Add integration → iCal Export.* Pick a feed name and the calendars to include. You can add several feeds. Under *Configure → Calendars and time window* you can change the calendars and the time window (default: 30 days back, 365 ahead).

The feed URLs contain the secret token, so they are not put in a notification (every HA user would see it). Open *Configure → Show feed URLs* (admins only) to get them:

- `/api/ical_export/<token>/all.ics` – all selected calendars combined
- `/api/ical_export/<token>/<calendar_object_id>.ics` – a single calendar

Each is shown as `https://` and `webcal://`.

## Subscribe in Apple Calendar

- **macOS:** File → New Calendar Subscription → paste URL.
- **iOS:** Settings → Calendar → Accounts → Add Account → Other → Add Subscribed Calendar.

Your HA must be reachable from the device (Nabu Casa, reverse proxy with HTTPS, or VPN). Apple refuses plain http on some versions for remote hosts, so prefer HTTPS.

## Security

Anyone with the URL can read the calendar. Treat it like a password.

- The token is 256 bits of randomness and is compared in constant time. Wrong tokens and unknown feeds get a plain 404.
- Because Apple Calendar can't send headers, the token has to be part of the URL path. That means **it also ends up in the access logs of any reverse proxy or CDN in front of HA** and in browser history if you open a feed in a browser. Don't share those logs, and prefer HTTPS so the token isn't sent in clear text.
- Feed URLs are only shown in *Configure → Show feed URLs*, which requires an admin. They are deliberately not put in notifications or diagnostics.
- Use *Configure → Generate a new token* to invalidate the old URLs (for example after they leaked). Every subscription then needs the new URL.
- If a calendar can't be read (e.g. right after a restart), the feed serves the last good copy or answers `503`. It never serves an empty calendar, which would make clients delete your events.

## Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt
pytest && ruff check .
docker compose -f dev/docker-compose.yml up   # HA on :8123 with demo calendars
```

---

# iCal Export (PL)

Integracja udostępnia wybrane kalendarze HA jako feedy iCal do subskrypcji w Apple Calendar. Zabezpieczenie: sekretny token w URL (rotacja w *Konfiguruj → Wygeneruj nowy token*). Instalacja przez HACS lub ręczne skopiowanie `custom_components/ical_export`; konfiguracja w *Ustawienia → Urządzenia i usługi*. Adresy URL (`https://` i `webcal://`) zobaczysz w *Konfiguruj → Pokaż adresy feedów* (tylko admin). HA musi być dostępny z internetu (Nabu Casa / reverse proxy z HTTPS) lub przez VPN.
