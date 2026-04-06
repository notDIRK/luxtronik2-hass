![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Docker](https://img.shields.io/badge/docker-supported-blue)

# luxtronik2-modbus-proxy

> Auf Deutsch lesen: [README.de.md](README.de.md)

A Modbus TCP proxy for Luxtronik 2.0 heat pump controllers. Translates the proprietary
Luxtronik binary protocol (port 8889) to standard Modbus TCP (port 502), enabling evcc,
Home Assistant, and other Modbus-capable tools to control older heat pumps from Alpha
Innotec, Novelan, Buderus, Nibe, Roth, Elco, and Wolf that lack native Modbus support.
Targets thousands of heat pumps that have no firmware upgrade path.

## Architecture

```
┌─────────────────────┐         ┌──────────────────────────┐
│  Luxtronik 2.0      │         │  luxtronik2-modbus-proxy │
│  Heat Pump          │ <────>  │                          │ <── evcc
│  Controller         │         │  Modbus TCP Server       │
│  port 8889          │         │  port 502                │ <── Home Assistant
└─────────────────────┘         └──────────────────────────┘
  proprietary protocol             standard Modbus TCP

Connect → Read/Write → Disconnect (coexists with HA integration)
```

## Quick Start

```bash
cp config.example.yaml config.yaml
# Edit config.yaml: set luxtronik_host to your heat pump's IP
docker compose up -d
```

## Features

- Modbus TCP server supporting FC3, FC4, FC6, FC16
- Connect-and-release polling (coexists with HA BenPru integration)
- SG-ready virtual register for evcc heat pump control
- 1,126 Luxtronik parameters selectable by name
- Configurable via YAML with environment variable overrides
- Docker and systemd deployment

## Documentation

- [Developer Quick Start](docs/en/quickstart.md) — build and run from source
- [User Guide](docs/en/user-guide.md) — install and configure (Docker)
- [systemd Service](docs/en/systemd.md) — Linux service deployment
- [evcc Integration](docs/en/evcc-integration.md) — heat pump control via evcc
- [HA Coexistence](docs/en/ha-coexistence.md) — running alongside Home Assistant

## License

MIT. See [LICENSE](LICENSE).
