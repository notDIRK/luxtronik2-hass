# Migration Guide: v1.1 → v1.2

This guide documents the upgrade from the old **`luxtronik2_modbus_proxy`** HACS integration (v1.1) to the new **`luxtronik2_hass`** HACS integration (v1.2).

## Who This Is For

You need this guide if **all** of the following apply:

- You previously installed the old HACS integration from `notDIRK/luxtronik2-modbus-proxy`
- You have an active config entry for **Luxtronik 2 Modbus Proxy** in Home Assistant
- You want to move to the actively maintained `luxtronik2-hass` repository

If you have never installed the old HACS integration, you do not need this guide — just follow the standard installation steps in [README.md](README.md).

## Blast Radius

The maintainer's live Home Assistant instance (HA 2026.4.1, Supervised) was measured before writing this guide. The migration touches a **very small** surface:

- **31 entities** from the old integration
- **1 dashboard file** referencing 32 of those entities (`dashboard-waermepumpe.yaml`)
- **0 automations**
- **0 scripts**
- **0 template sensors**

In other words: the only things that can break are the config entry itself and the dashboard. Nothing else in your Home Assistant setup depends on the old integration.

## Entity ID Stability — The Important Part

**Your user-visible entity IDs do not change across this migration.**

User-visible entity IDs (the ones dashboards and automations reference, e.g. `sensor.luxtronik_2_0_flow_temperature`) are derived from the **device-name slug**, not from the integration domain. Both the old and the new integration register the device with the same name, so the slug `luxtronik_2_0_*` is identical.

Only one entity contains the literal string `modbus_proxy`: `update.luxtronik_2_modbus_proxy_update` — the HACS update entity. It is not referenced by any dashboard, automation, script, or template sensor, so losing it is harmless.

## Step by Step

### 1. Backup (recommended)

Before you start, note which entities your dashboards/automations actually use. On the maintainer's instance this is `dashboard-waermepumpe.yaml` referencing 32 entities — all of them use the stable `luxtronik_2_0_*` prefix. If you have your own dashboard YAML, keep it open in a second tab so you can verify the entities still resolve after step 8.

If you were using the old repo's example dashboard file, you can still grab it from the archived repo: `https://github.com/notDIRK/luxtronik2-modbus-proxy/blob/main/docs/examples/dashboard-waermepumpe.yaml`.

### 2. Remove the old config entry

In Home Assistant:

1. Go to **Settings → Devices & Services**
2. Find the **Luxtronik 2 Modbus Proxy** integration tile
3. Click the ⋮ menu → **Delete**
4. Confirm

This removes the config entry and its 31 entities from the registry.

### 3. Uninstall the old HACS integration

In Home Assistant:

1. Go to **HACS → Integrations**
2. Find **Luxtronik 2 Modbus Proxy**
3. Click the ⋮ menu → **Remove**

### 4. Remove the old custom repository URL from HACS

1. Go to **HACS → Integrations → ⋮ menu → Custom repositories**
2. Find the entry for `notDIRK/luxtronik2-modbus-proxy`
3. Click the ❌ delete button

### 5. Add the new custom repository

1. Still in **HACS → Integrations → ⋮ menu → Custom repositories**
2. Add URL: `https://github.com/notDIRK/luxtronik2-hass`
3. Category: **Integration**
4. Click **ADD**

### 6. Install the new integration

1. Back in **HACS → Integrations**, search for **Luxtronik 2.0 (Home Assistant)**
2. Click **Download**
3. **Restart Home Assistant** when prompted

### 7. Add the new integration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Luxtronik 2.0**
3. Enter the IP address of your heat pump when prompted
4. The config flow should complete successfully

### 8. Verify

Verify the migration succeeded:

- **Settings → Devices & Services → Luxtronik 2.0** shows the device
- The device lists **31 entities**, all with IDs starting `luxtronik_2_0_*`
- Your existing dashboard renders without "entity not found" errors (if you reuse `dashboard-waermepumpe.yaml`, all 32 referenced entities should resolve)
- The `update.luxtronik_2_modbus_proxy_update` entity is gone (expected — it was the HACS update entity for the old repo)

## Rollback

If something goes wrong, you can always roll back:

1. Delete the new config entry (Settings → Devices & Services → Luxtronik 2.0 → ⋮ → Delete)
2. Uninstall the new integration in HACS
3. Re-add `https://github.com/notDIRK/luxtronik2-modbus-proxy` as a custom repository (it remains reachable in archived/read-only state)
4. Install the old version, restart HA, re-enter the IP

Your 31 entities will come back under the same `luxtronik_2_0_*` IDs.

## Why the Rename?

See the repository `README.md` for the full rationale. In short: the project is **Home-Assistant-first**, and the old name (`luxtronik2_modbus_proxy`) suggested the Modbus proxy was the main product — which is no longer true. The rebrand is cosmetic for the end user (entity IDs stable) but makes the project's status honest: HA integration is supported, the Modbus proxy is an unmaintained legacy byproduct.
