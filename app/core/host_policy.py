"""
Veritabanı host politikası (Faz 0.4 — sunucu üzerinden keyfi ağ erişimi / SSRF).

Kurallar:
  - DATALENS_ALLOWED_DB_HOSTS (virgülle ayrılmış) tanımlıysa yalnız bu hostlara izin verilir.
    Listedeki hostlar için IP kontrolü yapılmaz (ör. Docker ağındaki postgres-ortak).
  - Liste tanımsızsa hostname çözülür ve her IP kontrol edilir: loopback, link-local
    (169.254.169.254 metadata dahil), unspecified, multicast ve reserved reddedilir.
    Özel ağ (RFC1918) IP'leri bilinçli olarak serbest bırakılmıştır; Docker ağı için gerekli.
    Üretimde allowlist kullanılması önerilir.
  - Boş host "localhost" sayılır ve loopback olarak reddedilir.

Hata mesajları kullanıcıya gösterilebilir; IP ya da iç ayrıntı içermez.
"""
from __future__ import annotations

import ipaddress
import os
import socket


class HostPolicyError(ValueError):
    """Host politika tarafından reddedildi."""


def _allowlist() -> set[str]:
    raw = os.environ.get("DATALENS_ALLOWED_DB_HOSTS", "")
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def check_db_host(host: str | None) -> None:
    """Host kabul edilebilirse döner; değilse HostPolicyError fırlatır."""
    value = (host or "").strip().lower() or "localhost"

    allow = _allowlist()
    if allow:
        if value in allow:
            return
        raise HostPolicyError("Bu sunucuya bağlantıya izin verilmiyor")

    try:
        infos = socket.getaddrinfo(value, None)
    except socket.gaierror:
        raise HostPolicyError("Sunucu adı çözümlenemedi")

    for info in infos:
        raw_ip = info[4][0].split("%")[0]  # IPv6 scope kimliğini at
        ip = ipaddress.ip_address(raw_ip)
        if ip.is_loopback or ip.is_link_local or ip.is_unspecified \
                or ip.is_multicast or ip.is_reserved:
            raise HostPolicyError("Bu adres ağ politikası nedeniyle kullanılamaz")
