"""
Regresyon testi — connector_registry pip kurulum komutu.

Sorun: install_driver --break-system-packages bayrağıyla pip çalıştırıyordu. Uygulama
venv'de çalıştığı için bayrak gereksiz; sistem Python'una doğrudan kurulum yapar ve güvenlik
açısından zayıftır. Komut, subprocess çalıştırılmadan _pip_install_command ile kurulur.

Çalıştırma:
  cd <worktree> && venv/bin/python tests/unit/test_connector_install.py
"""
from __future__ import annotations

import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.core import connector_registry as cr  # noqa: E402


def test_pip_komutunda_break_system_packages_yok():
    """Her desteklenen sürücü için pip komutu bayraksız ve sys.executable ile kurulmalı."""
    for db_type, meta in cr.DRIVER_MAP.items():
        komut = cr._pip_install_command(meta["package"])
        assert "--break-system-packages" not in komut, f"{db_type}: {komut}"
        assert komut == [sys.executable, "-m", "pip", "install", meta["package"]], f"{db_type}: {komut}"


def test_install_driver_bayraksiz_komutla_calisir():
    """install_driver, yardımcının ürettiği komutu (bayraksız) subprocess'e vermeli."""
    gonderilen: list = []

    class _Sonuc:
        returncode = 1
        stderr = "test"

    def sahte_run(args, **kwargs):
        gonderilen.append(args)
        return _Sonuc()

    orijinal_run = cr.subprocess.run
    orijinal_kurulu = cr.ConnectorRegistry.driver_installed
    cr.subprocess.run = sahte_run
    cr.ConnectorRegistry.driver_installed = lambda self, db_type: False
    try:
        db_type = next(k for k, m in cr.DRIVER_MAP.items() if m["package"])
        cr.ConnectorRegistry().install_driver(db_type)
    finally:
        cr.subprocess.run = orijinal_run
        cr.ConnectorRegistry.driver_installed = orijinal_kurulu

    assert len(gonderilen) == 1, gonderilen
    assert "--break-system-packages" not in gonderilen[0], gonderilen[0]


TESTS = [test_pip_komutunda_break_system_packages_yok, test_install_driver_bayraksiz_komutla_calisir]


if __name__ == "__main__":
    basarili, basarisiz = 0, 0
    for t in TESTS:
        try:
            t()
            print("PASS", t.__name__)
            basarili += 1
        except Exception:
            print("FAIL", t.__name__)
            traceback.print_exc()
            basarisiz += 1
    print(f"\n{basarili} geçti, {basarisiz} başarısız")
    sys.exit(1 if basarisiz else 0)
