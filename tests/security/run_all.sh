#!/bin/sh
# Tüm güvenlik ve yetki testlerini çalıştırır (pytest gerektirmez).
cd "$(dirname "$0")/../.." || exit 1
fail=0
for t in tests/security/test_*.py tests/access/test_*.py tests/test_yetki.py; do
  if venv/bin/python "$t" >/tmp/_t.out 2>&1; then echo "PASS $t"; else echo "FAIL $t"; fail=1; tail -5 /tmp/_t.out; fi
done
rm -f /tmp/_t.out
exit $fail
