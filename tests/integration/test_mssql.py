"""
MSSQL entegrasyon testi (TOP ve OFFSET..FETCH yolları dahil).

Ortam değişkeni: DATALENS_IT_MSSQL_URL
Örnek: mssql+pyodbc://sa:DlTest_Pw_2026!@127.0.0.1:11433/dl_test?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes
Not: dl_test veritabanı konteynerde otomatik oluşmaz; bir kez elle oluşturun (CREATE DATABASE dl_test).
Gereken: ODBC Driver 18 for SQL Server ve pyodbc.

Çalıştırma: python tests/integration/test_mssql.py
"""
import sys

from _common import make_checks, run_suite

if __name__ == "__main__":
    sys.exit(run_suite("mssql", "DATALENS_IT_MSSQL_URL", "mssql", make_checks("mssql")))
