#!/bin/sh
# Test akışı. Kullanım: sh scripts/test.sh [all|security|integration]
#   security    -> tests/security/run_all.sh (ortam değişkeni gerektirmez)
#   integration -> tests/integration/test_*.py; her DB yalnız kendi DATALENS_IT_*_URL değişkeni
#                  tanımlıysa çalışır, yoksa "ATLANDI" yazıp geçer.
# Python: SUPERBI_PYTHON tanımlıysa o; yoksa venv/bin/python; o da yoksa python3.
set -u
cd "$(dirname "$0")/.." || exit 1

if [ -n "${SUPERBI_PYTHON:-}" ]; then
  PY="$SUPERBI_PYTHON"
elif [ -x venv/bin/python ]; then
  PY=venv/bin/python
else
  PY=python3
fi
export SUPERBI_PYTHON="$PY"

stage="${1:-all}"
fail=0

if [ "$stage" = "all" ] || [ "$stage" = "security" ]; then
  sh tests/security/run_all.sh || fail=1
fi

if [ "$stage" = "all" ] || [ "$stage" = "integration" ]; then
  for t in tests/integration/test_*.py; do
    # Her DB testi en fazla 5 dk; takılan bağlantı tüm akışı durdurmasın.
    timeout 300 "$PY" "$t" || { echo "FAIL $t"; fail=1; }
  done
fi

exit $fail
