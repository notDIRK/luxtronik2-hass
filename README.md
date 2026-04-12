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

The dashboard shows operating status, temperatures, pump states, operating hours, setpoints, and controls — all using the stable `luxtronik_2_0_*` entity IDs.

<details>
<summary>Click to expand dashboard YAML</summary>

```yaml
# Copy this into your dashboard's raw configuration editor.
# Replace "your-heatpump-ip" with your heat pump's IP address.
# Full file: docs/examples/dashboard-waermepumpe.yaml
```

See the full YAML file: [dashboard-waermepumpe.yaml](docs/examples/dashboard-waermepumpe.yaml)

</details>

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
