from __future__ import annotations

import base64
import io
import os
import socket
from functools import lru_cache
from urllib.parse import urlparse

from starlette.requests import Request

try:
    import qrcode
except Exception:  # pragma: no cover - optional desktop dependency
    qrcode = None


_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}


def _is_local_host(host: str) -> bool:
    normalized = str(host or "").strip().lower()
    return not normalized or normalized in _LOCAL_HOSTS or normalized == "0.0.0.0"


def _get_local_ip() -> str:
    env_ip = str(os.environ.get("FAB_LAN_IP", "")).strip()
    if env_ip and not _is_local_host(env_ip):
        return env_ip

    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        ip = probe.getsockname()[0]
        if ip and not _is_local_host(ip):
            return ip
    except OSError:
        pass
    finally:
        probe.close()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = str(info[4][0] or "").strip()
            if ip and not _is_local_host(ip) and not ip.startswith("169.254."):
                return ip
    except OSError:
        pass
    return ""


def _request_host(request: Request) -> str:
    return str(request.headers.get("host") or "").strip()


def _request_scheme(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-Proto")
    return str(forwarded or request.url.scheme or "http").strip() or "http"


def _port_from_request(request: Request) -> str:
    if request.url.port:
        return str(request.url.port)
    host = _request_host(request)
    if ":" in host and not host.startswith("["):
        return host.rsplit(":", 1)[1]
    return str(os.environ.get("FAB_PORT", "")).strip()


def _compose_url(scheme: str, host: str, port: str) -> str:
    scheme_name = (scheme or "http").strip() or "http"
    port_value = str(port or "").strip()
    if not port_value or (scheme_name == "http" and port_value == "80") or (scheme_name == "https" and port_value == "443"):
        return f"{scheme_name}://{host}"
    return f"{scheme_name}://{host}:{port_value}"


def _configured_mobile_url() -> str:
    for name in ("FAB_MOBILE_URL", "FAB_PUBLIC_URL"):
        raw = str(os.environ.get(name, "")).strip().rstrip("/")
        if not raw:
            continue
        parsed = urlparse(raw)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return raw
    return ""


def resolve_mobile_connect_url(request: Request) -> str:
    configured_url = _configured_mobile_url()
    if configured_url:
        return configured_url

    scheme = _request_scheme(request)
    request_host = _request_host(request)
    current_host = request.url.hostname or (request_host.rsplit(":", 1)[0] if request_host and not request_host.startswith("[") else request_host)
    port = _port_from_request(request)
    env_host = str(os.environ.get("FAB_HOST", "")).strip()

    if current_host and not _is_local_host(current_host):
        return _compose_url(scheme, current_host, port)

    if env_host and not _is_local_host(env_host):
        return _compose_url(scheme, env_host, port)

    lan_ip = _get_local_ip()
    if lan_ip:
        return _compose_url(scheme, lan_ip, port)

    return ""


@lru_cache(maxsize=16)
def build_mobile_connect_qr_data_uri(url: str) -> str:
    if not url or qrcode is None:
        return ""

    try:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=2,
        )
        qr.add_data(url)
        qr.make(fit=True)
        image = qr.make_image(fill_color="#0f172a", back_color="white").convert("RGB")

        payload = io.BytesIO()
        image.save(payload, format="PNG", optimize=True)
        encoded = base64.b64encode(payload.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    except Exception:
        return ""


def build_mobile_connect_context(request: Request) -> dict[str, str | bool]:
    url = resolve_mobile_connect_url(request)
    if not url:
        return {
            "mobile_connect_available": False,
            "mobile_connect_url": "",
            "mobile_connect_qr_uri": "",
            "mobile_connect_status": "Mode reseau requis",
        }

    qr_uri = build_mobile_connect_qr_data_uri(url)
    if qr_uri:
        return {
            "mobile_connect_available": True,
            "mobile_connect_url": url,
            "mobile_connect_qr_uri": qr_uri,
            "mobile_connect_status": "Connexion mobile",
        }

    return {
        "mobile_connect_available": False,
        "mobile_connect_url": url,
        "mobile_connect_qr_uri": "",
        "mobile_connect_status": "QR indisponible",
    }
