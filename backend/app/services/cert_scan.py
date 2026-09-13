"""
Daily TLS-certificate sweep over every real CustomerTenantInfo subdomain —
a bare handshake on :443 to read each host's own presented certificate, no
HTTP request involved. Deliberately a separate, much lighter operation than
tenant_info.py's fetch_tenant_info() (which fetches the real /info REST
endpoint over HTTP): a TLS handshake is what every browser tab does
implicitly on connect, an order of magnitude lighter than a full app-level
request, so unlike that file's "on-demand only, never scheduled" probe this
one runs on a daily schedule (see scheduler.py::_cert_scan).

Results are written directly onto the CustomerTenantInfo row that supplied
the subdomain — no accept/review step, unlike tenant_discovery.py's
candidate-guessing flow. There's no ambiguity here to guard against: every
host scanned is already a confirmed, on-file row, not a guessed candidate
that might belong to some other company's tenant.

Expiry/issuer are read even when the presented certificate wouldn't pass
normal verification (wrong host, self-signed, expired) — that mismatch is
itself exactly the kind of finding this tool exists to surface, not
something that should silently short-circuit the probe. See
_check_certificate_blocking() for why CERT_NONE is required, not laziness.
"""
import asyncio
import logging
import socket
import ssl
from datetime import datetime, timezone
from urllib.parse import urlparse

from cryptography import x509
from cryptography.x509.oid import NameOID
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.models.customer_tenant_info import CustomerTenantInfo

logger = logging.getLogger(__name__)

# Plain code constants, not DB-editable settings — same convention as
# TIER_UPGRADE_LIMITS elsewhere in this app. Imported by both desk.py (the
# flag) and routers/engineering.py (the tab's badges) so the two can never
# quietly disagree about what "expiring soon" means.
CERT_WARN_DAYS = 30
CERT_CRITICAL_DAYS = 7

_TIMEOUT = 10.0
_PORT = 443

# Bare TLS handshake, not a full app request — an order of magnitude
# lighter than tenant_discovery.py's Semaphore(5) probe, so a higher bound
# is fine while still not firing 100+ connections at once.
_CONCURRENCY = asyncio.Semaphore(10)


class CertCheckResult:
    def __init__(self, hostname: str, expires_at: datetime | None = None, issuer: str | None = None, error: str | None = None):
        self.hostname = hostname
        self.expires_at = expires_at
        self.issuer = issuer
        self.error = error


def _resolve_hostname(subdomain_or_url: str) -> str:
    """Mirrors tenant_info.py::_resolve_url()'s bare-code-vs-full-URL intent,
    but returns a bare hostname — a TLS handshake has no path. Deliberately
    does NOT modify _resolve_url() itself; the existing /info sync path
    stays untouched.

    A value containing "://" is a full URL (parsed for its host). A value
    containing "." with no scheme is treated as an already-complete FQDN
    verbatim — real bare tenant codes never contain a dot (confirmed
    against real values: "sfl", "gb-prod", "aecarriers", "kgjs"), so this
    can't misfire on one; it exists specifically so a customer's own domain
    (e.g. "vms.klaveness.com") isn't mangled into
    "vms.klaveness.com.dataloy.com". Anything else is a bare code, wrapped
    onto *.dataloy.com."""
    value = (subdomain_or_url or "").strip()
    if not value:
        return ""
    if "://" in value:
        host = urlparse(value).hostname
        return host or ""
    if "." in value:
        return value.split("/")[0]
    return f"{value}.dataloy.com"


def _check_certificate_blocking(hostname: str) -> CertCheckResult:
    try:
        # CERT_NONE + check_hostname=False are deliberate, not a security
        # bug: a mismatched, self-signed, or already-expired certificate is
        # exactly the finding this scan exists to surface. With normal
        # verification on, the handshake would raise before the cert could
        # be inspected at all, and every such host would just record an
        # opaque "TLS error" instead of a real expiry date. server_hostname
        # is still passed for SNI — Dataloy tenants sit behind shared load
        # balancers, so without it every host would return the balancer's
        # default cert instead of its own.
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with socket.create_connection((hostname, _PORT), timeout=_TIMEOUT) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as tls:
                # binary_form=True is required — the dict form of
                # getpeercert() is only populated on successful
                # verification, which CERT_NONE deliberately disables.
                der = tls.getpeercert(binary_form=True)
        if not der:
            return CertCheckResult(hostname, error="No certificate presented by host")

        cert = x509.load_der_x509_certificate(der)
        expires_at = getattr(cert, "not_valid_after_utc", None)
        if expires_at is None:
            # cryptography < 42.0 fallback — not_valid_after is documented
            # as UTC but naive; attach tzinfo explicitly rather than ever
            # writing a naive datetime into a timezone=True column.
            expires_at = cert.not_valid_after.replace(tzinfo=timezone.utc)

        cn = cert.issuer.get_attributes_for_oid(NameOID.COMMON_NAME)
        issuer = cn[0].value if cn else cert.issuer.rfc4514_string()

        return CertCheckResult(hostname, expires_at=expires_at, issuer=issuer)

    except socket.gaierror:
        return CertCheckResult(hostname, error=f"DNS lookup failed — {hostname} doesn't resolve")
    except ssl.SSLError as exc:
        return CertCheckResult(hostname, error=f"TLS handshake failed: {getattr(exc, 'reason', None) or exc}"[:500])
    except TimeoutError:
        return CertCheckResult(hostname, error=f"Timed out after {int(_TIMEOUT)}s — host may be VPN/firewall-restricted")
    except ConnectionRefusedError:
        return CertCheckResult(hostname, error=f"Connection refused on port {_PORT}")
    except OSError as exc:
        return CertCheckResult(hostname, error=f"Network error: {exc}"[:500])
    except Exception as exc:  # noqa: BLE001 — mirrors fetch_tenant_info()'s own catch-all tail
        logger.warning("Cert check failed for %s: %s", hostname, exc)
        return CertCheckResult(hostname, error=str(exc)[:400])


async def check_certificate(subdomain_or_url: str) -> CertCheckResult:
    """Never raises — always returns a CertCheckResult, mirroring
    tenant_info.py's TenantInfoResult convention. The socket work is
    blocking I/O and must not run on the event loop directly."""
    hostname = _resolve_hostname(subdomain_or_url)
    if not hostname:
        return CertCheckResult(hostname="", error="Subdomain isn't a resolvable hostname")
    return await asyncio.to_thread(_check_certificate_blocking, hostname)


def days_until_expiry(expires_at: datetime | None) -> int | None:
    if expires_at is None:
        return None
    now = datetime.now(timezone.utc)
    return (expires_at - now).days


def cert_status(expires_at: datetime | None, error: str | None, checked_at: datetime | None) -> str:
    """One of never_checked/error/expired/critical/expiring/valid, in that
    precedence order. Lives here (not duplicated in the router or desk.py)
    so the Engineering tab's badge and My Desk's flag can never disagree
    about what state a given row is in."""
    if checked_at is None:
        return "never_checked"
    if error is not None:
        return "error"
    days = days_until_expiry(expires_at)
    if days is None:
        return "error"
    if days < 0:
        return "expired"
    if days <= CERT_CRITICAL_DAYS:
        return "critical"
    if days <= CERT_WARN_DAYS:
        return "expiring"
    return "valid"


_scan_running = False


async def scan_all_certificates(db) -> dict:
    """Scans every real CustomerTenantInfo row (no filter — DEV included,
    real hosts with real certs). Writes results directly onto each row; on
    failure, cert_check_error is set but any previously-known
    cert_expires_at/cert_issuer is left untouched — a transient DNS blip
    shouldn't erase a known-good expiry date and silently drop a host out
    of the "expiring soon" flag. cert_checked_at always advances, so the
    staleness of a failed row is still visible."""
    global _scan_running
    if _scan_running:
        return {"skipped": "already running"}
    _scan_running = True
    started = datetime.now(timezone.utc)
    try:
        rows = (
            await db.execute(select(CustomerTenantInfo).options(joinedload(CustomerTenantInfo.customer)))
        ).scalars().all()

        async def _scan_one(row: CustomerTenantInfo) -> CertCheckResult:
            async with _CONCURRENCY:
                return await check_certificate(row.subdomain)

        results = await asyncio.gather(*(_scan_one(r) for r in rows))

        ok = errors = expiring_soon = expired = 0
        now = datetime.now(timezone.utc)
        for row, result in zip(rows, results):
            row.cert_checked_at = now
            if result.error:
                row.cert_check_error = result.error
                errors += 1
                continue
            row.cert_expires_at = result.expires_at
            row.cert_issuer = result.issuer
            row.cert_check_error = None
            ok += 1
            days = days_until_expiry(result.expires_at)
            if days is not None:
                if days < 0:
                    expired += 1
                elif days <= CERT_WARN_DAYS:
                    expiring_soon += 1

        await db.commit()
        duration = (datetime.now(timezone.utc) - started).total_seconds()
        return {
            "checked": len(rows), "ok": ok, "errors": errors,
            "expiring_soon": expiring_soon, "expired": expired,
            "duration_seconds": round(duration, 1),
        }
    finally:
        _scan_running = False


def is_scan_running() -> bool:
    return _scan_running
