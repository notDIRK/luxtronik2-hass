> Read in English: [README.md](README.md)

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Docker](https://img.shields.io/badge/docker-supported-blue)

# luxtronik2-modbus-proxy

Ein Modbus-TCP-Proxy fuer Luxtronik-2.0-Waermepumpenregler. Er uebersetzt das proprietaere
Luxtronik-Binaerprotokoll (Port 8889) in Standard-Modbus-TCP (Port 502) und ermoeglicht
damit evcc, Home Assistant und anderen Modbus-faehigen Tools die Steuerung aelterer
Waermepumpen von Alpha Innotec, Novelan, Buderus, Nibe, Roth, Elco und Wolf, die keine
native Modbus-Unterstuetzung bieten. Das Projekt richtet sich an tausende Waermepumpen,
fuer die kein Firmware-Upgrade moeglich ist.

## Architektur

```
┌─────────────────────┐         ┌──────────────────────────┐
│  Luxtronik 2.0      │         │  luxtronik2-modbus-proxy │
│  Waermepumpe        │ <────>  │                          │ <── evcc
│  Regler             │         │  Modbus-TCP-Server       │
│  Port 8889          │         │  Port 502                │ <── Home Assistant
└─────────────────────┘         └──────────────────────────┘
  proprietaeres Protokoll          Standard-Modbus-TCP

Connect → Read/Write → Disconnect (laeuft parallel zur HA-Integration)
```

## Schnellstart

```bash
cp config.example.yaml config.yaml
# config.yaml bearbeiten: luxtronik_host auf die IP der Waermepumpe setzen
docker compose up -d
```

## Funktionen

- Modbus-TCP-Server mit Unterstuetzung fuer FC3, FC4, FC6, FC16
- Connect-and-Release-Polling (laeuft parallel zur HA-BenPru-Integration)
- SG-Ready-Virtualregister fuer die Waermepumpensteuerung mit evcc
- 1.126 Luxtronik-Parameter per Name konfigurierbar
- Konfiguration per YAML mit Ueberschreibung durch Umgebungsvariablen
- Docker- und systemd-Deployment

## Dokumentation

- [Schnellstart](docs/de/quickstart.md) — Projekt klonen und starten
- [Benutzerhandbuch](docs/de/user-guide.md) — Installation und Konfiguration (Docker)
- [systemd-Dienst](docs/de/systemd.md) — Linux-Service-Installation
- [evcc-Integration](docs/de/evcc-integration.md) — Waermepumpensteuerung mit evcc
- [Parallelbetrieb mit HA](docs/de/ha-coexistence.md) — Betrieb neben Home Assistant

## Lizenz

MIT. Siehe [LICENSE](LICENSE).
