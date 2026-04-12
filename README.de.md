# Luxtronik 2.0 — Home Assistant Integration

**Home Assistant ist der primäre, aktiv gepflegte Weg, dieses Projekt zu nutzen.** Dieses Repository enthält eine HACS-Custom-Integration, die direkt mit Luxtronik‑2.0‑Wärmepumpensteuerungen kommuniziert und sie als Home‑Assistant‑Entities bereitstellt. Ein separater Modbus‑TCP‑Proxy existiert nur noch als nicht gepflegter Legacy‑Nebenschauplatz für Nutzer, die explizit rohen Modbus‑Zugriff benötigen.

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-41BDF5.svg)](https://www.home-assistant.io/)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Wenn du eine Luxtronik‑2.0‑Wärmepumpe von **Alpha Innotec, Novelan, Buderus, Nibe, Roth, Elco oder Wolf** besitzt, installiere die HACS‑Integration weiter unten — das ist der unterstützte Weg.

[English version → README.md](README.md)

---

## Drei Pfade

Dieses Projekt unterstützt drei Integrationspfade mit klar unterschiedlichem Reifegrad. Wähle den Pfad, der zu deinem Setup passt.

### Pfad 1: HACS Home Assistant Integration — ✅ Unterstützt

**Das ist der primäre Anwendungsfall und der einzige aktiv gepflegte Pfad.**

- Installation als HACS *Custom Repository* mit `https://github.com/notDIRK/luxtronik2-hass`
- Config‑Flow‑Oberfläche — nur die IP‑Adresse der Wärmepumpe eintragen, kein YAML
- **31+ Entities** verfügbar: Temperaturen, Betriebsmodi, Leistung, Status, Sollwerte, SG‑Ready
- Funktioniert mit Home Assistant **2024.1+** (getestet auf 2026.4.x)
- Python 3.12+ Laufzeit (entspricht HA Core)
- Spricht direkt mit der Wärmepumpe über die `luxtronik`-Bibliothek — keine zusätzlichen Dienste, keine Modbus‑Schicht

**Installation:**

1. In Home Assistant → HACS → Integrationen → ⋮ Menü → *Benutzerdefinierte Repositories*
2. `https://github.com/notDIRK/luxtronik2-hass` mit Kategorie **Integration** hinzufügen
3. **Luxtronik 2.0 (Home Assistant)** installieren
4. Home Assistant neu starten
5. Einstellungen → Geräte & Dienste → *Integration hinzufügen* → nach **Luxtronik 2.0** suchen
6. IP‑Adresse deiner Wärmepumpensteuerung eingeben

### Pfad 2: Legacy Modbus TCP Proxy — ⚠️ Experimentell

**Nicht gepflegter Legacy‑Nebenschauplatz.** Dieser existierte als eigenständiger Proxy vor der HACS‑Integration. Er wird nicht mehr aktiv gepflegt und lebt in einem separaten **archivierten** Repository.

Nutze diesen Pfad **nur**, wenn du explizit rohen Modbus‑TCP‑Zugriff brauchst — zum Beispiel für die Integration mit `evcc` oder einem anderen Modbus‑only‑Tool, das Home Assistant nicht ansprechen kann.

- Repository: [notDIRK/luxtronik2-modbus-proxy](https://github.com/notDIRK/luxtronik2-modbus-proxy) (archiviert, schreibgeschützt)
- Status: ⚠️ Experimentell — keine Bugfixes, keine neuen Features, kein Support
- Technologie: Python‑Proxy, der das Luxtronik‑Binärprotokoll (Port 8889) nach Modbus TCP (Port 502) übersetzt

Falls du den Proxy aktuell **zusammen mit** der HACS‑Integration betreibst, solltest du vollständig auf Pfad 1 migrieren — die Integration deckt alle Entities ab, die der Proxy bereitgestellt hat, und vermeidet den Single‑Connection‑Engpass.

### Pfad 3: Home Assistant Add‑on — 📋 Geplant für v1.3

Ein vollwertiges Home‑Assistant‑Add‑on (für HA OS und Supervised‑Installationen) ist **für v1.3 geplant**. Es wird die Integration als Supervisor‑Add‑on paketieren, sodass HA‑OS‑Nutzer es ohne HACS installieren können.

Dieser Pfad ist **noch nicht verfügbar**. Den Fortschritt kannst du in den Repository‑Meilensteinen verfolgen.

---

## Funktionen (Pfad 1 — HACS‑Integration)

- **Lese‑Sensoren**: Vor‑/Rücklauftemperatur, Außentemperatur, Warmwassertemperatur, Betriebsstunden, Stromverbrauch, Fehlerzustände, SG‑Ready‑Status
- **Steuer‑Entities**: Heizmodus, Warmwassermodus, SG‑Ready‑Modus, Temperatur‑Sollwerte
- **Schreibratenbegrenzung** zum Schutz der Steuerung vor Befehlsfluten
- **Single‑Connection‑sicher**: respektiert die One‑TCP‑Connection‑Beschränkung von Luxtronik 2.0 über Connect‑per‑Call + asyncio‑Lock
- **Englische und deutsche Übersetzungen** eingebaut
- **Stabile Entity‑IDs**: Entities verwenden das Gerätenamen‑Präfix `luxtronik_2_0_*` — sie ändern sich nicht, wenn die Integration umbenannt wird

### Dashboard-Vorschau

![Dashboard-Beispiel mit allen Luxtronik 2.0 Entities](docs/images/dashboard-demo.png)

### Dashboard einrichten

Ein fertiges Dashboard-YAML ist in diesem Repository enthalten. So richtest du es ein:

1. In Home Assistant: **Einstellungen → Dashboards → Dashboard hinzufügen**
2. Name vergeben (z.B. "Waermepumpe") und Icon wählen (`mdi:heat-pump`)
3. Neues Dashboard öffnen → **⋮** (oben rechts) → **Dashboard bearbeiten** → **⋮** → **Roher Konfigurationseditor**
4. Den gesamten Inhalt durch das YAML aus [`docs/examples/dashboard-waermepumpe.yaml`](docs/examples/dashboard-waermepumpe.yaml) ersetzen
5. In Zeile 11 `your-heatpump-ip` durch die tatsächliche IP-Adresse deiner Wärmepumpe ersetzen
6. **Speichern** klicken, dann **Fertig**

Das Dashboard zeigt Betriebsstatus, Temperaturen, Pumpenzustände, Betriebsstunden, Sollwerte und Steuerung — alles mit den stabilen `luxtronik_2_0_*` Entity-IDs.

<details>
<summary>Klicken um das Dashboard-YAML anzuzeigen</summary>

```yaml
# Kopiere dies in den Rohen Konfigurationseditor deines Dashboards.
# Ersetze "your-heatpump-ip" durch die IP-Adresse deiner Wärmepumpe.
# Vollständige Datei: docs/examples/dashboard-waermepumpe.yaml
```

Siehe die vollständige YAML-Datei: [dashboard-waermepumpe.yaml](docs/examples/dashboard-waermepumpe.yaml)

</details>

## Voraussetzungen

- Home Assistant **2024.1** oder neuer
- Eine im LAN erreichbare Luxtronik‑2.0‑Wärmepumpensteuerung
- Die IP‑Adresse der Wärmepumpe

## Kompatible Wärmepumpen

Alle Wärmepumpen mit Luxtronik‑2.0‑Steuerung, unter anderem Modelle von:

- Alpha Innotec
- Novelan
- Buderus (ausgewählte Modelle)
- Nibe (ausgewählte Modelle)
- Roth
- Elco
- Wolf

Wenn dein Gerät älter als Luxtronik 2.1 ist und keinen Firmware‑Upgrade‑Pfad hat, ist diese Integration für dich.

## Migration von v1.1

Falls du zuvor die alte `luxtronik2_modbus_proxy`‑HACS‑Integration (v1.1) verwendet hast, siehe **[MIGRATION.md](MIGRATION.md)** für die schrittweise Anleitung. Deine sichtbaren Entity‑IDs bleiben beim Upgrade stabil, weil sie vom Gerätenamen‑Slug abgeleitet werden, nicht vom Integrations‑Domain.

## Support

- Probleme: [GitHub Issues](https://github.com/notDIRK/luxtronik2-hass/issues)
- Diskussionen: [GitHub Discussions](https://github.com/notDIRK/luxtronik2-hass/discussions)

## Lizenz

[MIT](LICENSE) — passend zum Ökosystem der `luxtronik`‑Bibliothek.

## Danksagung

- [`luxtronik`](https://github.com/Bouni/python-luxtronik)‑Bibliothek von Bouni — der Binärprotokoll‑Client, auf dem diese Integration aufbaut
- Die Home‑Assistant‑Community
