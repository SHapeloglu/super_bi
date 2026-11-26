"""
Regresyon testi — üretim imajına PostgreSQL/MySQL/Oracle sürücüleri.

Sorun: sürücüler yalnız requirements-test.txt'te ve requirements.txt'te yorum satırıydı.
Üretim imajı (Dockerfile) yalnız requirements.txt kurar; konteyner çalışırken pip ile
sonradan kurulan sürücüler konteyner yeniden oluşturulunca kaybolur. Bu test,
requirements.txt'te sürücülerin yorum dışında bulunmasını ister.
pyodbc (MSSQL) bilinçli olarak yok: sistem ODBC sürücüsü gerektirir.

Çalıştırma:
  cd <proje> && <python> tests/security/test_runtime_drivers.py
"""
from __future__ import annotations

import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REQ = os.path.join(ROOT, "requirements.txt")
REQUIRED = ["psycopg2-binary", "PyMySQL", "oracledb"]


def _active_names() -> set[str]:
    names: set[str] = set()
    with open(REQ, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            name = line.split(">")[0].split("=")[0].split("<")[0].split("[")[0].strip()
            names.add(name.lower())
    return names


def test_driver_listed_as_active_requirement() -> None:
    active = _active_names()
    missing = [p for p in REQUIRED if p.lower() not in active]
    assert not missing, f"requirements.txt içinde yorum dışı değil: {missing}"


def main() -> int:
    fail = 0
    for name, fn in [("driver_active_requirement", test_driver_listed_as_active_requirement)]:
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError as e:
            fail += 1
            print(f"FAIL {name}: {e}")
        except Exception:
            fail += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"{1 - fail} geçti, {fail} başarısız")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
