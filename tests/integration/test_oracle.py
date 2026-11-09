"""
Oracle XE entegrasyon testi (FETCH FIRST ve OFFSET..FETCH yolları dahil).

Ortam değişkeni: DATALENS_IT_ORACLE_URL
Örnek: oracle+oracledb://dl_test:dl_test_pw@127.0.0.1:11521/?service_name=XEPDB1

Çalıştırma: python tests/integration/test_oracle.py
"""
import sys

from _common import make_checks, run_suite

if __name__ == "__main__":
    sys.exit(run_suite("oracle", "DATALENS_IT_ORACLE_URL", "oracle", make_checks("oracle")))
