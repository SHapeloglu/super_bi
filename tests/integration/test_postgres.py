"""
PostgreSQL entegrasyon testi.

Ortam değişkeni: DATALENS_IT_POSTGRES_URL
Örnek: postgresql+psycopg2://dl_test:dl_test_pw@127.0.0.1:15432/dl_test

Çalıştırma: python tests/integration/test_postgres.py
"""
import sys

from _common import make_checks, run_suite

if __name__ == "__main__":
    sys.exit(run_suite("postgresql", "DATALENS_IT_POSTGRES_URL", "postgresql",
                       make_checks("postgresql")))
