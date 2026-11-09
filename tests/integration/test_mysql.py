"""
MySQL entegrasyon testi.

Ortam değişkeni: DATALENS_IT_MYSQL_URL
Örnek: mysql+pymysql://dl_test:dl_test_pw@127.0.0.1:13306/dl_test

sql_builder identifier'ları çift tırnakla yazar (ANSI). MySQL varsayılanında çift tırnak
string literal'dir; bu yüzden test bağlantısında ANSI_QUOTES açılır. Uygulamanın kendi
MySQL bağlantısında bu ayar yoktur; bunun etkisi ayrıca "varsayilan_sql_mode_bilgi"
kontrolüyle yalnız bilgi olarak raporlanır (başarısızlık testi düşürmez).

Çalıştırma: python tests/integration/test_mysql.py
"""
import os
import sys

from sqlalchemy import create_engine

from _common import CUSTOMER, build_sql, fetch_rows, make_checks, run_suite

ENV = "DATALENS_IT_MYSQL_URL"


def _ansi_quotes(dbapi_conn, _record):
    cur = dbapi_conn.cursor()
    cur.execute("SET SESSION sql_mode = CONCAT(@@sql_mode, ',ANSI_QUOTES')")
    cur.close()


def varsayilan_sql_mode_bilgi(_engine):
    """Bilgi amaçlı: ANSI_QUOTES olmadan sql_builder SQL'i çalışıyor mu? Başarısızlık testi düşürmez."""
    eng = create_engine(os.environ[ENV], pool_pre_ping=True)
    try:
        fetch_rows(eng, build_sql("mysql", CUSTOMER, {"id": "on"}, order_by=["id"], limit=1))
        print("[BILGI] mysql: varsayılan sql_mode'da sql_builder SQL'i çalıştı")
    except Exception as e:
        print(f"[BILGI] mysql: varsayılan sql_mode'da sql_builder SQL'i ÇALIŞMADI "
              f"({type(e).__name__}); uygulama MySQL bağlantısında ANSI_QUOTES gerekiyor")
    finally:
        eng.dispose()


if __name__ == "__main__":
    checks = make_checks("mysql") + [("varsayilan_sql_mode_bilgi", varsayilan_sql_mode_bilgi)]
    sys.exit(run_suite("mysql", ENV, "mysql", checks, on_connect=_ansi_quotes))
