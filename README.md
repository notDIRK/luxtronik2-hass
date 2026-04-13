<!--
Keywords: luxtronik, luxtronik 2.0, luxtronik 2, heat pump, waermepumpe, wärmepumpe,
home assistant, hacs, hacs integration, custom integration, smart home,
alpha innotec, novelan, buderus, nibe, roth, elco, wolf,
sg-ready, sg ready, solar boost, energy management, energiemanagement,
modbus, modbus tcp, port 8889, binary protocol,
temperature sensor, heating control, hot water, warmwasser,
floor heating, fussbodenheizung, fußbodenheizung,
multi-layer buffer tank, mehrschichtspeicher, durchlauferhitzer,
solar surplus, solarüberschuss, netzeinspeisung, grid feed-in,
night heating pause, nacht heizungspause,
bath boost, badebooster, hot bath, heisses bad, warmwasser boost,
on-demand hot water, warmwasser auf knopfdruck,
parameter backup, parameter sicherung,
evcc, photovoltaik, pv überschuss
-->

<p align="center">
  <img src="custom_components/luxtronik2_hass/brand/icon@2x.png" alt="Luxtronik 2.0 Logo" width="128">
</p>

# Luxtronik 2.0 — Home Assistant Integration

**Home Assistant is the primary, actively maintained way to use this project.** This repository ships a HACS custom integration that talks directly to Luxtronik 2.0 heat pump controllers and exposes them as Home Assistant entities. A separate legacy Modbus TCP proxy exists as an unmaintained byproduct for users who specifically need raw Modbus access.

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-41BDF5.svg)](https://www.home-assistant.io/)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

If you own a Luxtronik 2.0 heat pump from **Alpha Innotec, Novelan, Buderus, Nibe, Roth, Elco, or Wolf**, install the HACS integration below — it is the supported path.

[Deutsche Version → README.de.md](README.de.md)

---

## Three Paths

This project supports three integration paths with clearly different maturity levels. Pick the one that matches your setup.

### Path 1: HACS Home Assistant Integration — ✅ Supported

**This is the primary use case and the only actively maintained path.**

- Install as a HACS *Custom Repository* pointing at `https://github.com/notDIRK/luxtronik2-hass`
- Config flow UI — enter your heat pump's IP address, no YAML
- **31+ entities** exposed: temperatures, operating modes, power, status, setpoints, SG-Ready
- Works with Home Assistant **2024.1+** (tested on 2026.4.x)
- Python 3.12+ runtime (matches HA Core)
- Talks directly to the heat pump via the `luxtronik` library — no extra services, no Modbus layer

**Installation:**

1. In Home Assistant → HACS → Integrations → ⋮ menu → *Custom repositories*
2. Add `https://github.com/notDIRK/luxtronik2-hass` with category **Integration**
3. Install **Luxtronik 2.0 (Home Assistant)**
4. Restart Home Assistant
5. Settings → Devices & Services → *Add Integration* → search for **Luxtronik 2.0**
6. Enter the IP address of your heat pump controller

### Path 2: Legacy Modbus TCP Proxy — ⚠️ Experimental

**Unmaintained legacy byproduct.** This existed as a standalone proxy before the HACS integration. It is no longer actively maintained and lives in a separate **archived** repository.

Use this path **only if** you specifically need raw Modbus TCP access — for example to integrate with `evcc` or another Modbus-only tool that cannot call Home Assistant.

- Repository: [notDIRK/luxtronik2-modbus-proxy](https://github.com/notDIRK/luxtronik2-modbus-proxy) (archived, read-only)
- Status: ⚠️ Experimental — no bug fixes, no new features, no support
- Technology: Python proxy translating Luxtronik binary protocol (port 8889) → Modbus TCP (port 502)

If you are currently running this proxy **together with** the HACS integration, consider migrating fully to Path 1 — the integration covers every entity the proxy exposed and removes the single-connection bottleneck.

### Path 3: Home Assistant Add-on — 📋 Planned v1.3

A first-class Home Assistant Add-on (for HA OS and Supervised installations) is **planned for v1.3**. It will package the integration as a supervisor add-on so users on HA OS can install it without HACS.

This path is **not yet available**. Track progress in the repository milestones.

---

## Features (Path 1 — HACS Integration)

- **Read-only sensors**: flow/return temperatures, outside temperature, hot water temperature, operating hours, power consumption, error states, SG-Ready status
- **Control entities**: heating mode, hot water mode, SG-Ready mode, temperature setpoints
- **[Bath Boost (Badebooster)](#bath-boost-badebooster)**: on-demand hot water heating with progress tracking — [details below](#bath-boost-badebooster)
- **[Smart Energy](#smart-energy)**: Solar Boost + Night Heating Pause — [details below](#smart-energy)
- **Write rate limiting** to protect the controller from command floods
- **Single-connection safe**: respects the Luxtronik 2.0 one-TCP-connection constraint via connect-per-call + asyncio lock
- **English + German translations** built in
- **Stable entity IDs**: entities use the device-name prefix `luxtronik_2_0_*` — they do not change if you rename the integration

### Dashboard Preview

![Dashboard example showing all Luxtronik 2.0 entities](docs/images/dashboard-demo.png)

### Dashboard Setup

A ready-to-use dashboard YAML is included in this repository. To set it up:

1. In Home Assistant, go to **Settings → Dashboards → Add Dashboard**
2. Choose a name (e.g. "Waermepumpe") and an icon (`mdi:heat-pump`)
3. Open the new dashboard → click **⋮** (top right) → **Edit Dashboard** → **⋮** → **Raw configuration editor**
4. Replace the entire content with the YAML from [`docs/examples/dashboard-waermepumpe.yaml`](docs/examples/dashboard-waermepumpe.yaml)
5. Replace `your-heatpump-ip` in line 11 with your actual heat pump IP address
6. Click **Save**, then **Done**

The dashboard shows operating status, temperatures, pump states, operating hours, setpoints, Smart Energy controls, and a 24-hour grid history graph — all using the stable `luxtronik_2_0_*` entity IDs.

**Two dashboard languages are available:**

| Language | File | Description |
|----------|------|-------------|
| **English** | [dashboard-heatpump-en.yaml](docs/examples/dashboard-heatpump-en.yaml) | All labels and descriptions in English |
| **Deutsch** | [dashboard-waermepumpe.yaml](docs/examples/dashboard-waermepumpe.yaml) | Alle Beschriftungen auf Deutsch |
| **Bath Boost** | [dashboard-bath-boost.yaml](docs/examples/dashboard-bath-boost.yaml) | Standalone card with progress display (add to any dashboard) |

Pick the one matching your Home Assistant language setting.

---

## Bath Boost (Badebooster)

**One button for a hot bath.** Press the Bath Boost button and the heat pump immediately starts heating your hot water tank to a higher target temperature. Once reached, everything returns to normal automatically.

**Quick start:**
1. Find the **Badebooster** button on your device page (Devices & Services > Luxtronik 2.0 > device)
2. Press it — done. The heat pump starts heating immediately.
3. Watch progress in the **Badebooster Status** sensor

**How it works:**

| Step | What happens |
|------|-------------|
| You press the button | Hot water mode switches to "Party" (forces immediate heating) and setpoint is raised to target temperature |
| Heating in progress | Status sensor shows "Active" with current temperature, progress %, and estimated remaining time |
| Target reached | Mode automatically returns to "Automatic", setpoint restored to normal |

**Default temperatures:**

| Setting | Default | Range | Where to change |
|---------|---------|-------|-----------------|
| Target temperature | 65.0 °C | 40–70 °C | Settings > Luxtronik 2.0 > Configure > Bath Boost |
| Normal temperature | 55.5 °C | 30–65 °C | Settings > Luxtronik 2.0 > Configure > Bath Boost |

**Entities created:**

| Entity | Type | Description |
|--------|------|-------------|
| `button.luxtronik_2_0_badebooster` | Button | Press to start heating |
| `sensor.luxtronik_2_0_badebooster_status` | Sensor | Shows "Active" or "Idle" with progress attributes |

The status sensor provides these attributes while active: `current_temperature`, `target_temperature`, `progress_percent`, `estimated_remaining_minutes`, `activated_at`.

**Dashboard card:** A ready-to-use dashboard card is included at [`docs/examples/dashboard-bath-boost.yaml`](docs/examples/dashboard-bath-boost.yaml). See the [Dashboard Setup](#dashboard-setup) section for how to add cards.

> **Note:** Bath Boost takes priority over Solar Boost. If Solar Boost is active when you press Bath Boost, your manual request wins.

---

## Smart Energy

Two optional automation features for heat pumps with **multi-layer buffer tanks and DHW (domestic hot water) heat exchangers**. Both can be enabled independently via **Settings → Devices & Services → Luxtronik 2.0 → Configure**.

### Solar Boost

Automatically raises the hot water setpoint when your solar system feeds surplus power into the grid — storing free solar energy in the buffer tank instead of exporting it.

- **Trigger:** Grid feed-in exceeds a configurable threshold (default: 1500 W)
- **Action:** Hot water setpoint raised from normal (default: 55.5 °C) to boost temperature (default: 65.0 °C)
- **Minimum runtime:** Once activated, boost stays active for a configurable duration (default: 30 min) to prevent rapid cycling during cloud cover
- **Grid sensor convention:** Positive values = consumption (buying), negative values = feed-in (selling). Example: `sensor.grid_total = -2000` means 2000 W feed-in
- **Spike protection:** A 60-second debounce prevents false triggers from short grid spikes (e.g. when the compressor stops and briefly causes feed-in overshoot)

#### Hot Water Hysteresis

Your Luxtronik controller has a **WW hysteresis** setting (typically 5 K) that affects when hot water heating actually starts. The controller only begins heating when the tank temperature drops below the setpoint by the hysteresis amount.

**Example:** With a setpoint of 55.5 °C and 5 K hysteresis, the controller will not start heating until the temperature drops to **50.5 °C** (55.5 - 5.0 = 50.5).

This matters for Solar Boost because:
- Solar Boost raises the setpoint (e.g. to 65 °C), but the heat pump will not actually start heating until the tank drops to 60 °C (with 5 K hysteresis)
- If your tank is already at 58 °C, Solar Boost will raise the setpoint but no heating occurs — the surplus solar energy is still exported to the grid

**Configuration:** Enter your controller's WW hysteresis value in **Settings > Devices & Services > Luxtronik 2.0 > Configure > Solar Boost**. The dashboard will then display the effective start temperature. You can find the hysteresis value on your controller display under *Parameters > Hot Water > Hysteresis*.

**Dashboard visualization:**

| Symbol | Meaning |
|--------|---------|
| 🔌 **Netzbezug: 1078 W** | Consuming from grid (positive value) |
| ☀️ **Einspeisung: 2000 W** | Feeding into grid (negative value) |
| 🟢 Boost condition met | Feed-in > threshold |
| 🟡 Below threshold | Feed-in present but below threshold |
| 🔴 No solar surplus | Consuming from grid |

### Night Heating Pause

Automatically disables floor heating during night hours to prevent the heating circuit from cooling down the buffer tank overnight. This preserves hot water for the morning — critical for systems where the floor heating and DHW share the same buffer.

- **Default window:** 18:00 – 09:00 (configurable)
- **Action:** Heating mode set to "Off" during the window, restored to "Automatic" outside
- **Why:** In a multi-layer buffer tank with DHW heat exchanger, the floor heating loop can drain heat from the buffer overnight, leaving no hot water in the morning

### Configuration

All features are configured in the integration's options flow:

1. **Settings → Devices & Services → Luxtronik 2.0 → Configure**
2. Select **Solar Boost**, **Night Heating Pause**, or **Bath Boost** from the menu
3. Enable the feature and adjust thresholds/temperatures/times
4. The dashboard shows toggle switches, grid status, and a 24-hour history graph

Smart Energy switches can also be toggled at runtime via the switch entities (`switch.luxtronik_2_0_solar_boost`, `switch.luxtronik_2_0_night_heating_pause`).

## Requirements

- Home Assistant **2024.1** or newer
- A Luxtronik 2.0 heat pump controller reachable on your LAN
- The heat pump's IP address

## Compatible Heat Pumps

Any heat pump with a Luxtronik 2.0 controller, including models from:

- Alpha Innotec
- Novelan
- Buderus (selected models)
- Nibe (selected models)
- Roth
- Elco
- Wolf

If your unit predates Luxtronik 2.1 and has no firmware upgrade path, this integration is for you.

## Migration from v1.1

If you previously used the old `luxtronik2_modbus_proxy` HACS integration (v1.1), see **[MIGRATION.md](MIGRATION.md)** for the step-by-step upgrade path. Your user-visible entity IDs stay stable across the upgrade because they derive from the device-name slug, not the integration domain.

## Support

- Issues: [GitHub Issues](https://github.com/notDIRK/luxtronik2-hass/issues)
- Discussions: [GitHub Discussions](https://github.com/notDIRK/luxtronik2-hass/discussions)

## License

[MIT](LICENSE) — matching the `luxtronik` library ecosystem.

## Credits

- [`luxtronik`](https://github.com/Bouni/python-luxtronik) library by Bouni — the binary protocol client this integration depends on
- The Home Assistant community
