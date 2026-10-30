# ISS Tracker for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories/)
[![GitHub release](https://img.shields.io/github/v/release/kedube/ha-iss-tracker)](https://github.com/kedube/ha-iss-tracker/releases)
[![CI](https://github.com/kedube/ha-iss-tracker/actions/workflows/validate.yml/badge.svg)](https://github.com/kedube/ha-iss-tracker/actions/workflows/validate.yml)
![Home Assistant 2025.6+](https://img.shields.io/badge/Home%20Assistant-2025.6%2B-41BDF5.svg)
[![License](https://img.shields.io/github/license/kedube/ha-iss-tracker)](LICENSE)

![The ISS Tracker: chase view of the station flying along its orbit](docs/images/chase-view.jpg)

Know when to step outside and look up. This custom integration predicts when the
International Space Station will be **visible** from your home: above your horizon,
lit by the Sun, while your sky is dark. It gives you advance notice, the direction to
look, how high it will climb, and how bright it will be, a calendar of the visible
passes, and an **ISS Tracker** page with a 3D Earth that shows the station flying round
it at its true altitude.

All prediction runs locally inside Home Assistant using SGP4, the standard model for
published satellite orbital elements and the one that pass-prediction sites such as
Heavens-Above and N2YO also rely on. Predictions need only the station's published
orbit, downloaded a few times a day and cached so they keep working through internet
outages. The 3D globe additionally loads map imagery in your browser (see
[Data sources](#data-sources-and-etiquette)).

## Why another ISS integration?

| | Built-in **ISS** integration | **Satellite Tracker (N2YO)** | **This integration** |
|---|---|---|---|
| Current position | Yes (Open Notify) | Yes (N2YO) | Yes, computed locally |
| Visible pass predictions | No (Open Notify retired its pass API) | Yes, computed by N2YO's servers | Yes, computed locally |
| Works offline | No | No | Yes, from cached orbit data (up to 14 days old) |
| Needs an account / API key | No | Yes | No (N2YO key optional) |
| Sends your location to a third party | No | Yes, every poll | No (unless you add an N2YO key)¹ |
| Rate limits | n/a | 100 pass requests/hour, shared by all satellites | Downloads orbit data every 6 h |
| 3D globe | No | No | Yes: day and night, city lights, orbit in 3D, countdown |

¹ The globe's imagery tiles come from public map servers, so like any online map they
see which area you are looking at.

## How it works

```
CelesTrak (OMM XML)  ─┐
wheretheiss.at (TLE) ─┼─► validate ─► cache (.storage) ─► SGP4 ─► passes for your location
N2YO (TLE, optional) ─┘                                      │
                                                             └─► live position every 10–60 s
```

1. **Orbit data.** Every 6 hours the integration downloads the ISS's latest mean orbital
   elements, from CelesTrak first and then the backup sources. Each download is checked
   (right object, plausible orbit, valid checksums), and newer elements are never replaced
   by older ones from a lagging mirror.
2. **Propagation.** SGP4 moves the station along its orbit. Your location (latitude,
   longitude, elevation on the WGS-84 ellipsoid) gives azimuth and elevation for every
   instant.
3. **Visibility.** A pass counts as visible while the station is above your horizon mask,
   **in sunlight** (not in Earth's shadow), and **your Sun is below** the darkness
   threshold. The station shines only by reflected sunlight, so the best views come in the
   hour or two after sunset or before sunrise.
4. **Brightness.** Visual magnitude is estimated from range and Sun angle (lower numbers
   are brighter; -3 to -4 is a brilliant pass).
5. **Rolling forecast.** Passes are recomputed every 30 minutes and whenever new orbit
   data arrives, so far-off predictions sharpen as they approach.

### Accuracy

The engine was cross-checked against [Skyfield](https://rhodesmill.org/skyfield/), using
the JPL DE421 ephemeris, at six locations across 10 days (see
`scripts/validate_against_skyfield.py`):

| Quantity | Largest difference from Skyfield |
|---|---|
| Where the station is in your sky | 0.004° |
| Sun elevation (darkness test) | 0.006° |
| Rise, peak and set times | 0.4 s |
| Start and end of the visible window | ~1 s (the reference's sampling step) |
| Passes found or missed | identical |

The limit on real-world accuracy is the orbit data, not the maths. In testing, two
element sets published a day apart agreed to within about 2 seconds for every visible pass
over the following 10 days. The larger risk is a **reboost** or debris-avoidance
manoeuvre: the station's orbit changes, and later passes can shift by tens of seconds per
day until new orbit data is published, usually within hours. The integration picks that up
on its next download. Each pass carries a `confidence` attribute based on how far it lies
from the orbit data's epoch:

* `high`: within 3 days.
* `medium`: 3–7 days.
* `low`: beyond a week. Use these for planning and check again closer to the date; the
  forecast window goes up to 30 days.

These confidence bands are a practical rule of thumb, not a formal error bound.

Brightness estimates are good to about half a magnitude; the real brightness depends on
how the station's solar arrays are angled. The Earth's shadow edge is treated as sharp,
whereas the real station fades over a few seconds.

## Installation

### Marketplace or HACS (recommended)

Home Assistant 2026.11 replaced HACS with its built-in **Marketplace**. This repository
is not in the Marketplace catalog (or the HACS default store), so add it as a custom
repository. The quickest way is this button, which opens it in the Marketplace (in HACS
before 2026.11) on your Home Assistant:

[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=kedube&repository=ha-iss-tracker&category=integration)

Or add it by hand. On Home Assistant 2026.11 or later:

1. Go to **Settings → Marketplace** and select **Add from link** (top right).
2. Under **GitHub link**, enter `https://github.com/kedube/ha-iss-tracker` and select
   **Add**. The first time, the Marketplace asks you to connect GitHub, which it needs
   for custom repositories.
3. Open **ISS Tracker**, select **Install**, and confirm.
4. Restart Home Assistant if a repair asks you to.
5. [Add the integration](#setup).

On older versions, with HACS:

1. In Home Assistant, open **HACS**.
2. Open the menu (**⋮**, top right) and choose **Custom repositories**.
3. Enter `https://github.com/kedube/ha-iss-tracker`, choose the type **Integration**, and
   select **Add**.
4. Search HACS for **ISS Tracker**, open it and select **Download**.
5. Restart Home Assistant.
6. [Add the integration](#setup).

Installed it with HACS already? Updating Home Assistant to 2026.11 moves it to the
Marketplace by itself: it stays installed and keeps getting updates.

Installed it before 1.02, when it was called **ISS Pass Prediction**? The rename gave
it a new domain (`iss_tracker`), so it can't take over the old entries. Delete the
**ISS Pass Prediction** entries under **Settings → Devices & services**, delete the
`custom_components/iss_pass_prediction` folder if it is still there, and restart; then
install ISS Tracker and add your locations again. Give each location the same name as
before (the old default was **ISS**, now it is **Home**) and its entity IDs stay the
same, so automations keep working. The exceptions are the four entities that describe
the station rather than your location, whose names now start with ISS: **ISS elevation**,
**ISS position**, **ISS above horizon** and **ISS visible now**. Check automations that
use them, or change their entity IDs back under **Settings → Entities**. Re-import the
[blueprint](#notifications), and pick the location in any globe card that names one.

### Updating

The Marketplace (HACS before 2026.11) offers each new release as an update under
**Settings → Updates** and shows its release notes. Install the update, restart Home
Assistant, and then reload any dashboards you have open so they load the new version
of the globe.

### Manual installation

1. Download the source code of the
   [latest release](https://github.com/kedube/ha-iss-tracker/releases/latest).
2. Copy its `custom_components/iss_tracker` folder into the `custom_components` folder
   of your Home Assistant configuration directory, creating that folder if needed.
3. Restart Home Assistant.

Manual installs don't get update notifications. Repeat these steps to update.

## Setup

**Settings → Devices & services → Add integration → ISS Tracker.** The location
defaults to your Home Assistant home; you can add more locations (a cabin, a dark-sky
site) with **Add location** on the integration's page. To correct a location's
coordinates or elevation later, choose **Reconfigure** on its entry: its entities,
automations and dashboard cards keep working.

### Options

| Option | Default | Meaning |
|---|---|---|
| Horizon mask | 10° | The station only counts as visible above this elevation. NASA's Spot the Station also uses 10°. |
| Minimum peak elevation | 20° | Skip low passes that never climb higher than this. |
| Darkness threshold | -6° | The Sun must be at least this far below the horizon (end of civil twilight). Try -3° to include brighter twilight passes. |
| Minimum visible time | 60 s | Skip fleeting passes. |
| Forecast window | 10 days | 1–30 days. See **Accuracy**. |
| Advance notice | 15 min | When **Visible pass soon** turns on. |
| Show ISS Tracker in the sidebar | on | Adds the **ISS Tracker** page to the sidebar. Turn off to remove it; the globe card stays available. The page stays open while a location reloads after an options change. If another dashboard already uses the address `/iss-tracker`, the page is not added (a warning is logged). |
| Show visible passes in the calendar | on | Adds the location's **ISS visible passes** calendar (see [Calendar](#calendar)). Turn off to remove it. |
| Units | Automatic | Distances and speeds on the globe (altitude, speed, distance from you): **Automatic** follows Home Assistant's unit system, or choose **Metric** (km, km/h) or **Imperial** (mi, mph). Entity attributes stay metric (`range_km`, `altitude_km`, `speed_km_s`). |
| N2YO API key | none | Optional: adds N2YO as a backup orbit source, for every location (they share the orbit data), and checks this integration's predictions against N2YO's once a day. |

## Entities

Shown here for a location named **Home**, with Home Assistant set to English. The
integration is also translated into German, Dutch, French, Spanish, Italian, Polish,
Brazilian Portuguese and Swedish; in those languages new entities get their names, and
entity IDs, in that language.

| Entity | What it tells you |
|---|---|
| `sensor.home_next_visible_pass` | Start time of the next visible pass (or the one under way). Attributes give start/peak/end time, direction and elevation, `duration_seconds`, `magnitude`, `disappears_into_shadow`, `confidence`, and `upcoming`, a list of the next qualifying passes in the window (up to 20). |
| `sensor.home_next_visible_pass_peak_elevation` | How high it climbs (90° is straight overhead). |
| `sensor.home_next_visible_pass_brightness` | Estimated magnitude (lower = brighter). |
| `sensor.home_next_visible_pass_duration` | How long it is visible. |
| `sensor.home_next_pass` | Next pass above the horizon mask, visible or not (useful for radio). |
| `sensor.home_iss_elevation` | The station's elevation in your sky right now, with azimuth, direction, range and whether it is sunlit. |
| `binary_sensor.home_visible_pass_soon` | On from the advance-notice time until the visible pass ends. With an advance notice longer than the gap between two passes (about 90 minutes), it stays on from one pass to the next; the [blueprint](#notifications) still announces each one. |
| `binary_sensor.home_iss_visible_now` | On while a visible pass is under way. |
| `binary_sensor.home_iss_above_horizon` | On while the station is above your horizon mask, lit or not. |
| `calendar.home_iss_visible_passes` | Every visible pass in the forecast window as an event, with where to look; on while one is under way. See [Calendar](#calendar). |
| `device_tracker.home_iss_position` | Ground point beneath the station, for map cards. |
| `sensor.home_orbital_elements_epoch` | Diagnostic: age and source of the orbit data, with `age_days`, `stale` and `last_download_error`. When predictions pause, it stays available to say why until Home Assistant restarts or the location reloads (an options change reloads it); then the repair issue and the location's entry under **Devices & services** say why. |
| `sensor.home_n2yo_prediction_difference` | Diagnostic (only with an N2YO key): largest angle between N2YO's prediction and this one over the next three days. Near the peak, 1° is roughly 1 s of timing. Further ahead, predictions from different orbit data drift apart (more so across a reboost), so the attributes also give the largest difference over the whole window (`max_difference`), how many days ahead it was (`max_difference_days_ahead`) and the median. |

The live position updates every 60 seconds, and every 10 seconds while the station is
above your horizon. Its fast-changing attributes (direction, range, altitude, speed) are
not recorded. To keep your database smaller still, you can exclude
`device_tracker.home_iss_position` and `sensor.home_iss_elevation` from the
[recorder](https://www.home-assistant.io/integrations/recorder/).

If no fresh orbit data can be downloaded for 14 days (a long internet outage, say),
predictions would be misleading, so they pause: the entities go unavailable, a repair
issue under **Settings → Repairs** explains why, and the globe says so instead of
counting down. Everything resumes by itself once a download succeeds.

## ISS Tracker and globe card

The integration adds an **ISS Tracker** page to the sidebar (switch it off in the
options) and an **ISS globe** card for dashboards. Both show the same live 3D Earth:

* **The real sky.** NASA's Blue Marble from space, sharpening to Sentinel-2 satellite
  imagery (or Esri's, down to individual houses) as you zoom in. The night side is drawn
  from the real Sun position, with NASA's Black Marble city lights, a warm band of
  twilight along the terminator and an atmosphere that glows on the sunlit limb.
* **The station at its true altitude**, about 420 km up, lit when the Sun reaches it and
  dark in Earth's shadow, with its orbit as a glowing ribbon in space: blue in sunlight,
  violet in shadow, with clock times every 15 minutes and a fading trail behind.
* **Your visibility cone**: the cone of sky above your home, reaching up to the
  station's altitude, inside which it is at least 10° up. The **intercept**, the next
  pass through it, is drawn in gold when it is a pass you can see, and in silver when it
  is not, labelled with why: too low or too brief for your options, daylight, a sky too
  bright for your darkness threshold, or Earth's shadow. The next pass you can see is
  always drawn in gold, with its time. A dashed heading shows the orbit it comes in on.
* **Countdown** to the next visible pass, the next time it crosses your sky, and live
  directions ("Look SW, 34° up") while it is overhead.
* **Where to look**: a sky chart of the pass from your home, with a live dot during it.
* **Preview the pass**: fast-forwards the Earth, the Sun and the station to your next
  visible pass (or any pass in the list, however far ahead in the forecast window), then
  plays the pass slowly from above your home.
* **Camera modes**: your location, follow the ISS, or fly alongside it. Zoom out for the
  globe and in for a flat map; drag to rotate, right-drag or two fingers to tilt.

The page and the card follow your Home Assistant language: English, German, Dutch,
French, Spanish, Italian, Polish, Brazilian Portuguese or Swedish (other languages
show English).

| Night side, your visibility cone and the intercept | Previewing a pass from above home |
|---|---|
| ![Globe at night](docs/images/globe-night.jpg) | ![Preview of a pass](docs/images/preview-pass.jpg) |
| **Following the station across Asia** | **Zoomed in on home (Esri imagery)** |
| ![Following the ISS](docs/images/follow-view.jpg) | ![Close up](docs/images/closeup-home.jpg) |

<p align="center"><img src="docs/images/phone.jpg" width="260" alt="ISS Tracker on a phone"></p>

### Card

The card is listed in the dashboard editor as **ISS globe** and has a visual editor.
In YAML:

```yaml
type: custom:iss-globe-card
view: follow            # home (default), follow or chase
imagery: satellite      # satellite (default), esri or streets
# entry_id: ...         # which location, if you have several
# labels: true          # place names and borders
# show_track: true      # orbit and clock times
# show_night: true      # day and night
# show_footprint: true  # area that can see the ISS
# show_home_zone: true  # visibility cone
# show_countdown: true
# show_stats: true
# cooperative_gestures: false  # require two fingers / Ctrl+scroll to move the map
# height: 420           # masonry dashboards; sections grids and panel views fill their space
```

![The globe card on a dashboard](docs/images/dashboard-card.jpg)

The globe needs a browser with WebGL 2 (any current browser, including the Companion
app). It redraws only a few times a second while idle, stops when it is off screen,
and frees its graphics memory shortly after you leave the page.

## Notifications

Import the blueprint:

[![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fkedube%2Fha-iss-tracker%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fiss_tracker%2Fnotify_visible_pass.yaml)

It sends a Companion-app notification when a pass is about to start, and optionally a daily
heads-up:

> **ISS visible in 15 min**
> Look up at 7:15 PM. Appears in the WNW (10° up), climbs to 67° in the SSW, fades into
> Earth's shadow in the ESE. Visible for 6.2 min, brightness -3.4.

Or build your own; the timestamp sensor works directly with a time trigger:

```yaml
triggers:
  - trigger: time
    at:
      entity_id: sensor.home_next_visible_pass
      offset: "-00:10:00"
```

The [calendar](#calendar) works with a calendar trigger, which fires for every pass,
even with an offset longer than the gap between two passes.

## Calendar

Each location has an **ISS visible passes** calendar, listed in Home Assistant's
**Calendar** with your other calendars (switch it off in the options). It holds the same
passes as `sensor.home_next_visible_pass`: every visible pass in the forecast window that
your options let through. Each event runs from when the station appears to when it
disappears, and says where to look:

> **ISS visible pass · up to 67°**
> Appears in the WNW 10° up, climbs to 67° in the SSW, fades into Earth's shadow in the
> ESE.
> Brightness -3.4 · high confidence

The events are refined as new orbit data arrives, and a pass drops off the calendar soon
after it is over. While predictions are paused, the calendar is unavailable and empty.
Like the globe, the events follow Home Assistant's language (other languages show
English); after changing the language, reload the location or restart Home Assistant.

An automation that sends a notification ten minutes before each pass:

```yaml
triggers:
  - trigger: calendar
    event: start
    offset: "-0:10:0"
    entity_id: calendar.home_iss_visible_passes
actions:
  - action: notify.mobile_app_your_phone  # your phone's notify action
    data:
      title: "{{ trigger.calendar_event.summary }}"
      message: >-
        Look up at {{ as_timestamp(trigger.calendar_event.start) | timestamp_custom('%-I:%M %p') }}.
        {{ trigger.calendar_event.description }}
```

## Dashboard

Besides the [globe card](#card), the sensors work with Home Assistant's own cards:

```yaml
type: markdown
content: >
  {% set p = 'sensor.home_next_visible_pass' %}
  {% if states(p) not in ['unknown', 'unavailable'] %}
  | When | Look | Peak | Brightness | Confidence |
  |---|---|---|---|---|
  {% for q in state_attr(p, 'upcoming') %}| {{ as_timestamp(q.start) | timestamp_custom('%a %-d %b, %-I:%M %p') }} | {{ q.start_direction }} → {{ q.end_direction }} | {{ q.peak_elevation | round(0) }}° {{ q.peak_direction }} | {{ q.magnitude }} | {{ q.confidence }} |
  {% endfor %}
  {% else %}No visible ISS passes in the forecast window.{% endif %}
```

```yaml
type: map
entities:
  - device_tracker.home_iss_position
hours_to_show: 2
```

## Data sources and etiquette

* [CelesTrak](https://celestrak.org/NORAD/documentation/gp-data-formats.php) GP data in
  CCSDS OMM XML, the format CelesTrak recommends now that the legacy TLE format has run
  out of catalogue numbers. CelesTrak asks clients to download at most once every two
  hours. This integration downloads every six hours and shares one download across all
  configured locations. After a source refuses a request (HTTP 403, 404 or 429) or sends
  unusable data, it is left alone for two hours. A source that cannot be reached
  (timeout, connection error or HTTP 5xx) is tried again no sooner than five minutes
  later: in practice at the next half-hourly refresh, or while Home Assistant retries
  setup. A mirror whose data has stopped updating does not stop the search: the next
  source is asked.
* [wheretheiss.at](https://wheretheiss.at/w/developer): backup TLE source.
* [N2YO](https://www.n2yo.com/api/): optional, with your own API key.

The 3D globe loads its imagery directly in your browser, apart from the city lights,
which come with the integration:

| Layer | Source | Terms |
|---|---|---|
| Earth from space | [NASA GIBS](https://www.earthdata.nasa.gov/gibs) Blue Marble | NASA imagery, free to use with credit |
| City lights (bundled) | NASA Black Marble 2016 via [GIBS](https://www.earthdata.nasa.gov/gibs) | Public domain (NASA); credited on the map |
| Close-up (default) | [Sentinel-2 cloudless 2025](https://s2maps.eu) by EOX IT Services | CC BY-NC-SA 4.0: personal, non-commercial use |
| Close-up (Esri option) | [Esri World Imagery](https://www.arcgis.com/home/item.html?id=10df2279f9684e4a9f6a7f08febac2a9) | Esri's terms of use apply; choose it only if they suit you |
| Place names, borders, street map | OpenStreetMap, through Home Assistant's own map tile service | © OpenStreetMap contributors |

Credits for whichever layers are on screen are shown in the corner of the map.

## Development

```bash
python3.14 -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt
pytest
node --test "tests/js/*.test.mjs"   # the globe: geometry, sky chart, WebGL layers, view, panel, translations
```

The unit tests compare the engine with stored Skyfield results, so they need neither
Skyfield nor an ephemeris. To re-run the full cross-check against live orbit data:

```bash
pip install skyfield
python scripts/validate_against_skyfield.py --days 10   # downloads de421.bsp (~17 MB) on first run
```

### Translations

What Home Assistant shows for the integration (setup, options, entity names, the repair
notice, the calendar's events) is in `custom_components/iss_tracker/translations/`, one
JSON file per language, with `strings.json` as the English source. The calendar's
wording, under `common`, repeats the globe's. The sidebar page and the card have their
own text in `custom_components/iss_tracker/frontend/translations/`: English in `en.js`,
every other language in a JSON file with the same keys.

To add a language, copy a JSON file in both folders to the new language's code,
translate the values and keep each `{placeholder}` as it is. Then add the code to
`LANGUAGES` in `frontend/iss-i18n.js`. The JS tests check that every language has every
key, the same placeholders and the plural forms it needs; the Python tests check the
calendar's words the same way.

### Releasing

Releases are numbered `MAJOR.MM` with no `v` (1.00, 1.01, … 1.99, then 2.00), and the
number comes from `version` in `manifest.json`. When every check passes on `main`, CI
publishes that version as a release, unless it has been released already; until the
number goes up, pushes release nothing.

```bash
python scripts/version.py bump     # manifest.json to the next version, e.g. 1.00 -> 1.01
python scripts/version.py status   # whether pushing to main will release it
```

## Credits and licence

Orbit propagation uses [`sgp4`](https://pypi.org/project/sgp4/) by Brandon Rhodes, the
official Vallado SGP4 implementation. The globe is drawn with
[MapLibre GL JS](https://maplibre.org) 6.11.2 (BSD-3-Clause, bundled under
`custom_components/iss_tracker/frontend/vendor/`). The city lights are NASA Black
Marble via GIBS (public domain), bundled under
`custom_components/iss_tracker/frontend/img/`. The icon and logo
(`custom_components/iss_tracker/brand/`, drawn by `scripts/make_brand.py`) use
[Natural Earth](https://www.naturalearthdata.com) coastlines (public domain) and the
[Space Grotesk](https://github.com/floriankarsten/space-grotesk) typeface (SIL Open Font
License 1.1). Licensed under the GNU GPL v3; see `LICENSE`.
