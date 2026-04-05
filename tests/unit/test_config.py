"""Unit tests for ProxyConfig and configure_logging.

Tests verify that:
- Config loads from a YAML file with correct values
- Defaults are applied for optional fields
- Validation rejects poll_interval below 10
- Environment variables with LUXTRONIK_ prefix override YAML values
- configure_logging succeeds at DEBUG and INFO levels
"""

import pytest

from luxtronik2_modbus_proxy.config import ProxyConfig, load_config
from luxtronik2_modbus_proxy.logging_config import configure_logging


def test_config_loads_luxtronik_host_from_yaml(tmp_path):
    """ProxyConfig loads luxtronik_host from a YAML file at a specified path."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("luxtronik_host: '192.168.x.x'\n")
    config = load_config(str(config_file))
    assert config.luxtronik_host == "192.168.x.x"


def test_config_defaults(tmp_path):
    """ProxyConfig uses correct defaults for optional fields."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("luxtronik_host: '192.168.x.x'\n")
    config = load_config(str(config_file))
    assert config.luxtronik_port == 8889
    assert config.modbus_port == 502
    assert config.poll_interval == 30
    assert config.log_level == "INFO"
    assert config.enable_writes is False
    assert config.write_rate_limit == 60


def test_config_rejects_low_poll_interval(tmp_path):
    """ProxyConfig rejects poll_interval below 10 with ValidationError."""
    from pydantic import ValidationError

    config_file = tmp_path / "config.yaml"
    config_file.write_text("luxtronik_host: '192.168.x.x'\npoll_interval: 5\n")
    with pytest.raises(ValidationError):
        load_config(str(config_file))


def test_config_env_var_override(tmp_path, monkeypatch):
    """ProxyConfig env vars with LUXTRONIK_ prefix override YAML values."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("luxtronik_host: '192.168.x.x'\npoll_interval: 30\n")
    monkeypatch.setenv("LUXTRONIK_POLL_INTERVAL", "60")
    config = load_config(str(config_file))
    assert config.poll_interval == 60


def test_configure_logging_debug():
    """configure_logging('DEBUG') succeeds without error."""
    configure_logging("DEBUG")


def test_configure_logging_info():
    """configure_logging('INFO') succeeds without error."""
    configure_logging("INFO")


# --- RegistersConfig tests (Phase 2, Plan 02) ---


def test_registers_config_default_empty_parameters(tmp_path):
    """ProxyConfig with no registers section has registers.parameters == []."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("luxtronik_host: '192.168.x.x'\n")
    config = load_config(str(config_file))
    assert config.registers.parameters == []


def test_registers_config_loads_parameters_from_yaml(tmp_path):
    """ProxyConfig with registers.parameters list loads the parameter names correctly."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "luxtronik_host: '192.168.x.x'\n"
        "registers:\n"
        "  parameters:\n"
        "    - ID_Einst_WK_akt\n"
    )
    config = load_config(str(config_file))
    assert config.registers.parameters == ["ID_Einst_WK_akt"]


def test_registers_config_loads_multiple_parameters(tmp_path):
    """ProxyConfig with multiple registers.parameters entries loads all names."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "luxtronik_host: '192.168.x.x'\n"
        "registers:\n"
        "  parameters:\n"
        "    - ID_Einst_WK_akt\n"
        "    - ID_Ba_Hz_MK3_akt\n"
    )
    config = load_config(str(config_file))
    assert "ID_Einst_WK_akt" in config.registers.parameters
    assert "ID_Ba_Hz_MK3_akt" in config.registers.parameters
