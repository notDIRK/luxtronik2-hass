<!--
Keywords: home assistant, hacs, luxtronik, luxtronik 2, alpha innotec, novelan, buderus,
nibe, roth, elco, wolf, wärmepumpe, waermepumpe, heat pump, modbus, modbus tcp, evcc,
sg-ready, sg ready, wärmepumpen integration, ha custom component, sole wasser,
wasser wasser, luft wasser, heizungssteuerung, energiemanagement, pv-überschuss,
photovoltaik, smart home, homeassistant
-->

> Read in English: [README.md](README.md)

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Docker](https://img.shields.io/badge/docker-supported-blue)
![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange)
![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue)

# Luxtronik 2 Modbus Proxy + Home Assistant Integration

**Zwei Nutzungswege — such dir den passenden aus:**

1. **Home Assistant HACS-Integration** (empfohlen für die meisten) — Installation in 2 Minuten über HACS, IP eingeben, fertig. Zeigt Sensoren, steuert Heiz-/Warmwassermodus/SG-Ready, sichert Parameter. **Kein Modbus-Proxy nötig.**
2. **Standalone Modbus-TCP-Proxy** — für evcc, Grafana oder jedes andere Modbus-fähige Tool. Läuft als Docker-Container oder systemd-Dienst.

Funktioniert mit **Alpha Innotec, Novelan, Buderus, Nibe, Roth, Elco und Wolf** Wärmepumpen mit Luxtronik-2.0-Regler — tausende Geräte ohne Firmware-Upgrade-Pfad.

![Dashboard Beispiel](docs/images/dashboard-waermepumpe.png)

---

## 🏠 Home Assistant Integration (HACS)

**Du brauchst KEIN Modbus, KEIN evcc, nichts.** Die HACS-Integration spricht direkt mit deiner Wärmepumpe und stellt alles als native HA-Entitäten bereit.

### Was du sofort bekommst

| Kategorie | Entitäten |
|-----------|-----------|
| **Temperaturen** | Außen, Vorlauf, Rücklauf, Warmwasser, Sole Ein/Aus (6 Sensoren) |
| **Status** | Betriebsmodus, EVU-Sperre, Status-Dauer, Kompressor, Pumpen |
| **Pumpen** | Heizungs-Umwälzpumpe (HUP), Warmwasser-Umwälzpumpe (BUP), Zirkulationspumpe (ZIP), Zusatz-Umwälzpumpe (ZUP), Solepumpe (VBO), Mischer HK1 |
| **Betriebsstunden** | Wärmepumpe gesamt, Verdichter, Heizkreis, Warmwasser |
| **Steuerung** | Heizmodus, Warmwassermodus, SG-Ready, Warmwasser-Solltemperatur, Heizkurven-Verschiebung |
| **Sicherung** | Ein-Klick Parameter-Sicherung als JSON-Datei |
| **Erweiterbar** | +1.367 zusätzliche Parameter über die HA-Entitätsverwaltung aktivierbar |

Alle Entity-Namen und Übersetzungen auf **Deutsch und Englisch** (weitere Sprachen willkommen).

### Installation in 2 Minuten

1. HACS öffnen → **Integrationen** → **⋮** → **Benutzerdefinierte Repositories**
2. `https://github.com/notDIRK/luxtronik2-modbus-proxy` als Typ **Integration** hinzufügen
3. Integration herunterladen, Home Assistant neu starten
4. **Einstellungen → Geräte & Dienste → Integration hinzufügen → "Luxtronik 2 Modbus Proxy"**
5. IP-Adresse der Wärmepumpe eingeben. Fertig.

### Beispiel-Dashboard

Ein fertiges Dashboard-YAML liegt unter [`docs/examples/dashboard-waermepumpe.yaml`](docs/examples/dashboard-waermepumpe.yaml) — kopiere es in den Raw-Konfigurationseditor eines neuen Dashboards und du bekommst den obigen Screenshot.

---

## ⚙️ Standalone Modbus-TCP-Proxy

Wenn du die Wärmepumpe mit **evcc**, Grafana oder einem anderen Modbus-TCP-Client **ohne** Home Assistant nutzen willst, starte den Standalone-Proxy.

### Architektur

```
┌─────────────────────┐         ┌──────────────────────────┐
│  Luxtronik 2.0      │         │  luxtronik2-modbus-proxy │
│  Wärmepumpe         │ <────>  │                          │ <── evcc
│  Regler             │         │  Modbus-TCP-Server       │
│  Port 8889          │         │  Port 502                │ <── Grafana / andere
└─────────────────────┘         └──────────────────────────┘
  proprietäres Protokoll           Standard-Modbus-TCP

Connect → Read/Write → Disconnect (läuft parallel zur HA-Integration)
```

### Schnellstart

```bash
cp config.example.yaml config.yaml
# config.yaml bearbeiten: luxtronik_host auf die IP der Wärmepumpe setzen
docker compose up -d
```

### Proxy-Funktionen

- Modbus-TCP-Server mit Unterstützung für FC3, FC4, FC6, FC16
- Connect-and-Release-Polling (läuft parallel zur HA-BenPru-Integration und zur HACS-Integration oben)
- SG-Ready-Virtualregister für die Wärmepumpensteuerung mit evcc
- 1.126 Luxtronik-Parameter per Name konfigurierbar
- Konfiguration per YAML mit Überschreibung durch Umgebungsvariablen
- Docker- und systemd-Deployment
- Schreibratenbegrenzung zum Schutz des Regler-NAND-Flash

---

## 📚 Dokumentation

- [Schnellstart](docs/de/quickstart.md) — Projekt klonen und starten
- [Benutzerhandbuch](docs/de/user-guide.md) — Installation und Konfiguration (Docker)
- [systemd-Dienst](docs/de/systemd.md) — Linux-Service-Installation
- [evcc-Integration](docs/de/evcc-integration.md) — Wärmepumpensteuerung mit evcc
- [Parallelbetrieb mit HA](docs/de/ha-coexistence.md) — Betrieb neben Home Assistant

## 🤝 Kompatibilität

| Hersteller | Luxtronik 2.0 Regler | Anmerkung |
|------------|----------------------|-----------|
| Alpha Innotec | ✅ Ja | Getestet mit MSW 14 (Sole/Wasser) |
| Novelan | ✅ Ja | Gleiche Reglerplattform |
| Buderus | ✅ Ja | Ältere Luxtronik-Modelle |
| Nibe | ✅ Ja | Nur Luxtronik-basierte Modelle |
| Roth, Elco, Wolf | ✅ Ja | Gleiche Reglerplattform |

Voraussetzung: Luxtronik-2.0-Firmware auf Port 8889.

## 🔐 Sicherheit

Dies ist ein **öffentliches Repository**. Ein Pre-Commit-Hook scannt jeden Commit auf sensible Muster (echte IPs, Hostnames, Tokens) und blockiert den Commit im Treffer-Fall. Beiträge willkommen — bitte gleiches Prinzip beachten.

## Lizenz

MIT. Siehe [LICENSE](LICENSE).
