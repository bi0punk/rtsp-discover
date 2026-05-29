#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Probe de cámaras IP: prueba múltiples endpoints HTTP/RTSP para detectar si existe transmisión.

Características:
- Soporta placeholders [USERNAME], [PASSWORD], [CHANNEL]
- Prueba con una credencial (y opcionalmente anónimo)
- Detecta:
  - JPEG (snapshot único)
  - MJPEG (stream multipart o chunk con JPEG)
  - RTSP (vía ffprobe si está disponible, o OpenCV como fallback)
  - HTTP video genérico (intenta abrir con OpenCV)
- Timeout configurable
- Exporta CSV opcional

Requisitos recomendados:
- Python 3.10+
- pip install requests opencv-python
- (Opcional) ffprobe instalado: apt install ffmpeg
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from typing import List, Optional, Tuple
from urllib.parse import quote

import requests

try:
    import cv2  # type: ignore
    HAS_CV2 = True
except Exception:
    HAS_CV2 = False


# =========================
# Config de endpoints
# =========================

ENDPOINTS = [
    ("0001 / 960P Audio Mini / China Cam", "JPEG", "http", "snap.jpg?usr=[USERNAME]&pwd=[PASSWORD]"),
    ("1000 / Fluereon / Generic IP Cam", "FFMPEG", "rtsp", "/1"),
    ("16CH", "JPEG", "http", "cgi-bin/webra_fcgi.fcgi?api=get_jpeg_raw&chno=[CHANNEL]"),
    ("Bseries", "FFMPEG", "http", "/"),
    ("c6c-P / H.264", "VLC", "rtsp", "mpeg4cif"),
    ("DAHAUS", "JPEG", "http", "cgi-bin/snapshot.cgi?chn=[CHANNEL]&u=[USERNAME]&p=[PASSWORD]"),
    ("DF-ICAM", "FFMPEG", "rtsp", "/mpeg4cif"),
    ("FOCUS 66 / HIDVCAM", "MJPEG", "http", "/media/?action=stream"),
    ("Gen 1 / Generic IP Cam", "FFMPEG", "rtsp", "/live/ch00_0"),
    ("Generic IP Cam (cam1/mpeg4)", "FFMPEG", "rtsp", "cam1/mpeg4"),
    ("Generic IP Cam ONVIF service", "FFMPEG", "http", "/onvif/dev%C4%B1ce_service"),
    ("Generic IP Cam /video", "FFMPEG", "http", "/video"),
    ("Generic IP Cam img/video.sav", "FFMPEG", "rtsp", "/img/video.sav"),
    ("Generic IP Cam live/ch00_1", "FFMPEG", "rtsp", "/live/ch00_1"),
    ("Generic PTZ Shenzhen", "MJPEG", "rtsp", "/mpeg4"),
    ("Generic IP Cam profile1", "FFMPEG", "rtsp", "/profile1"),
    ("IPC365", "VLC", "rtsp", "ch0_0.h264"),
    ("IPELA HD / V380", "FFMPEG", "rtsp", "/11"),
    ("nolist", "JPEG", "http", "/cgi-bin/webra_fcgi.fcgi?api=get_jpeg_raw&chno=0"),
    ("ONVIF / Other", "FFMPEG", "rtsp", "/ucast/11"),
    ("Other cam1/mpeg4 with query creds", "FFMPEG", "rtsp", "cam1/mpeg4?user=[USERNAME]&pwd=[PASSWORD]"),
    ("Other / ResX-IP-Cams", "FFMPEG", "rtsp", "/0/av0"),
    ("Other snap.jpg JpegSize", "JPEG", "http", "snap.jpg?JpegSize=M"),
    ("Other snap.jpg usr/pwd", "JPEG", "http", "/snap.jpg?usr=[USERNAME]&pwd="),
    ("PTZ", "FFMPEG", "rtsp", "/cam1/mpeg4"),
    ("rtsp realmonitor", "FFMPEG", "rtsp", "/realmonitor?channel=0&stream=0.sdp"),
    ("rtsp user_password_channel", "FFMPEG", "rtsp", "/user=[USERNAME]_password=[PASSWORD]_channel=1_stream=1.sdp"),
]


# =========================
# Data classes
# =========================

@dataclass
class Credential:
    label: str
    username: str
    password: str

@dataclass
class ProbeResult:
    endpoint_name: str
    media_type: str
    protocol: str
    credential_label: str
    url: str
    ok: bool
    method_used: str
    status_code: Optional[int]
    content_type: Optional[str]
    detail: str
    elapsed_ms: int


# =========================
# Helpers
# =========================

def normalize_base_url(host: str, scheme: str) -> str:
    host = host.strip()
    host = re.sub(r"^\w+://", "", host)
    return f"{scheme}://{host}"

def join_url(base: str, path: str) -> str:
    if path.startswith("/"):
        return base.rstrip("/") + path
    return base.rstrip("/") + "/" + path

def fill_placeholders(path: str, cred: Credential, channel: int) -> str:
    u = quote(cred.username, safe="")
    p = quote(cred.password, safe="")
    return path.replace("[USERNAME]", u).replace("[PASSWORD]", p).replace("[CHANNEL]", str(channel))

def build_url(host: str, protocol: str, path: str, cred: Credential, channel: int, embed_rtsp_auth: bool) -> str:
    filled = fill_placeholders(path, cred, channel)
    base = normalize_base_url(host, protocol)

    if protocol == "rtsp" and embed_rtsp_auth and "[USERNAME]" not in path and "[PASSWORD]" not in path:
        host_only = re.sub(r"^\w+://", "", base)
        if cred.username or cred.password:
            auth = f"{quote(cred.username, safe='')}:{quote(cred.password, safe='')}@"
            base = f"rtsp://{auth}{host_only}"

    return join_url(base, filled)


# =========================
# Probes HTTP
# =========================

def probe_http_jpeg(url: str, timeout: int, auth: Optional[Tuple[str, str]]) -> Tuple[bool, Optional[int], Optional[str], str]:
    try:
        r = requests.get(url, timeout=timeout, stream=True, auth=auth)
        ct = r.headers.get("Content-Type", "")
        if r.status_code != 200:
            return False, r.status_code, ct, f"HTTP {r.status_code}"

        chunk = r.raw.read(64)
        if len(chunk) >= 3 and chunk[0] == 0xFF and chunk[1] == 0xD8 and chunk[2] == 0xFF:
            return True, r.status_code, ct, "JPEG detectado por magic bytes"

        if "image/jpeg" in ct.lower() or "image/jpg" in ct.lower():
            return True, r.status_code, ct, "Content-Type image/jpeg"

        return False, r.status_code, ct, "No parece JPEG"
    except requests.RequestException as e:
        return False, None, None, f"requests error: {e}"

def probe_http_mjpeg(url: str, timeout: int, auth: Optional[Tuple[str, str]]) -> Tuple[bool, Optional[int], Optional[str], str]:
    try:
        r = requests.get(url, timeout=timeout, stream=True, auth=auth)
        ct = r.headers.get("Content-Type", "")
        if r.status_code != 200:
            return False, r.status_code, ct, f"HTTP {r.status_code}"

        if "multipart" in ct.lower() and "mixed" in ct.lower():
            return True, r.status_code, ct, "MJPEG multipart detectado"

        data = r.raw.read(4096)
        if b"\xff\xd8" in data and b"\xff\xd9" in data:
            return True, r.status_code, ct, "MJPEG/stream con frame JPEG detectado"

        if b"\xff\xd8" in data:
            return True, r.status_code, ct, "Stream con inicio de JPEG detectado"

        return False, r.status_code, ct, "No se detectó MJPEG"
    except requests.RequestException as e:
        return False, None, None, f"requests error: {e}"

def probe_http_generic_video_with_cv2(url: str, timeout: int) -> Tuple[bool, Optional[int], Optional[str], str]:
    if not HAS_CV2:
        return False, None, None, "OpenCV no instalado (opencv-python)"
    try:
        cap = cv2.VideoCapture(url)
        t0 = time.time()
        while time.time() - t0 < timeout:
            ok, frame = cap.read()
            if ok and frame is not None:
                cap.release()
                return True, None, None, f"Frame leído con OpenCV {frame.shape if hasattr(frame, 'shape') else ''}"
            time.sleep(0.2)
        cap.release()
        return False, None, None, "Sin frame por OpenCV en timeout"
    except Exception as e:
        return False, None, None, f"cv2 error: {e}"


# =========================
# Probes RTSP
# =========================

def ffprobe_available() -> bool:
    return shutil.which("ffprobe") is not None

def probe_rtsp_ffprobe(url: str, timeout: int) -> Tuple[bool, str]:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-rtsp_transport", "tcp",
        "-timeout", str(timeout * 1_000_000),
        "-show_streams",
        "-select_streams", "v:0",
        url,
    ]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 3)
        if p.returncode == 0 and "codec_type=video" in p.stdout:
            return True, "ffprobe detectó stream de video"
        detail = (p.stderr or p.stdout or "").strip()
        return False, f"ffprobe fallo: {detail[:300]}"
    except subprocess.TimeoutExpired:
        return False, "ffprobe timeout"
    except Exception as e:
        return False, f"ffprobe error: {e}"

def probe_rtsp_cv2(url: str, timeout: int) -> Tuple[bool, str]:
    if not HAS_CV2:
        return False, "OpenCV no instalado (opencv-python)"
    try:
        cap = cv2.VideoCapture(url)
        t0 = time.time()
        while time.time() - t0 < timeout:
            ok, frame = cap.read()
            if ok and frame is not None:
                cap.release()
                return True, f"Frame leído con OpenCV {frame.shape if hasattr(frame, 'shape') else ''}"
            time.sleep(0.2)
        cap.release()
        return False, "Sin frame por OpenCV en timeout"
    except Exception as e:
        return False, f"cv2 error: {e}"


# =========================
# Dispatcher
# =========================

def probe_endpoint(
    host: str,
    endpoint: Tuple[str, str, str, str],
    cred: Credential,
    channel: int,
    timeout: int,
    http_basic_auth: bool,
    embed_rtsp_auth: bool,
) -> ProbeResult:
    name, media_type, protocol, path = endpoint
    url = build_url(host, protocol, path, cred, channel, embed_rtsp_auth=embed_rtsp_auth)

    auth = (cred.username, cred.password) if http_basic_auth and (cred.username or cred.password) else None

    t0 = time.time()
    ok = False
    method_used = ""
    status_code = None
    content_type = None
    detail = ""

    try:
        if protocol == "http":
            if media_type.upper() == "JPEG":
                method_used = "requests-jpeg"
                ok, status_code, content_type, detail = probe_http_jpeg(url, timeout, auth)
            elif media_type.upper() == "MJPEG":
                method_used = "requests-mjpeg"
                ok, status_code, content_type, detail = probe_http_mjpeg(url, timeout, auth)
            else:
                try:
                    r = requests.get(url, timeout=timeout, stream=True, auth=auth)
                    status_code = r.status_code
                    content_type = r.headers.get("Content-Type", "")
                    if r.status_code == 200:
                        if "xml" in (content_type or "").lower() or "onvif" in url.lower():
                            ok = False
                            method_used = "requests-http"
                            detail = "Endpoint ONVIF/servicio detectado (no stream de video)"
                        else:
                            data = r.raw.read(4096)
                            if b"\xff\xd8" in data:
                                ok = True
                                method_used = "requests-http"
                                detail = "Bytes de JPEG detectados"
                            else:
                                method_used = "cv2-http"
                                ok, _, _, detail = probe_http_generic_video_with_cv2(url, timeout)
                    else:
                        ok = False
                        method_used = "requests-http"
                        detail = f"HTTP {r.status_code}"
                except requests.RequestException as e:
                    method_used = "requests-http"
                    ok = False
                    detail = f"requests error: {e}"

        elif protocol == "rtsp":
            if ffprobe_available():
                method_used = "ffprobe-rtsp"
                ok, detail = probe_rtsp_ffprobe(url, timeout)
                if not ok:
                    method_used = "cv2-rtsp"
                    ok2, detail2 = probe_rtsp_cv2(url, timeout)
                    if ok2:
                        ok = True
                        detail = detail2
                    else:
                        detail = f"{detail} | fallback cv2: {detail2}"
            else:
                method_used = "cv2-rtsp"
                ok, detail = probe_rtsp_cv2(url, timeout)
        else:
            method_used = "none"
            ok = False
            detail = f"Protocolo no soportado: {protocol}"

    except Exception as e:
        ok = False
        detail = f"error inesperado: {e}"

    elapsed_ms = int((time.time() - t0) * 1000)

    return ProbeResult(
        endpoint_name=name,
        media_type=media_type,
        protocol=protocol,
        credential_label=cred.label,
        url=url,
        ok=ok,
        method_used=method_used,
        status_code=status_code,
        content_type=content_type,
        detail=detail,
        elapsed_ms=elapsed_ms,
    )


# =========================
# CLI
# =========================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prueba endpoints de cámaras IP (HTTP/RTSP) para detectar transmisión."
    )
    parser.add_argument("--ip", required=True, help="IP o host de la cámara (ej: 192.168.1.50)")
    parser.add_argument("--port-http", type=int, default=80, help="Puerto HTTP por defecto")
    parser.add_argument("--port-rtsp", type=int, default=554, help="Puerto RTSP por defecto")
    parser.add_argument("--channel", type=int, default=0, help="Canal para endpoints [CHANNEL]")

    # Única credencial
    parser.add_argument("--user", default="", help="Usuario")
    parser.add_argument("--passw", default="", help="Password")

    parser.add_argument("--timeout", type=int, default=5, help="Timeout por prueba (segundos)")
    parser.add_argument("--http-basic-auth", action="store_true", help="Además intenta HTTP Basic Auth")
    parser.add_argument("--no-embed-rtsp-auth", action="store_true", help="No insertar user:pass@ en URL RTSP")
    parser.add_argument("--no-anon", action="store_true", help="No probar acceso anónimo")
    parser.add_argument("--only-success", action="store_true", help="Muestra solo resultados OK")
    parser.add_argument("--csv", default="", help="Ruta CSV de salida (opcional)")
    parser.add_argument("--verbose", action="store_true", help="Muestra URLs completas")

    return parser.parse_args()

def host_with_default_port(ip_or_host: str, proto: str, port_http: int, port_rtsp: int) -> str:
    if re.match(r"^\[.*\]:\d+$", ip_or_host) or re.match(r"^[^/]+:\d+$", ip_or_host):
        return ip_or_host
    if proto == "http":
        return f"{ip_or_host}:{port_http}"
    if proto == "rtsp":
        return f"{ip_or_host}:{port_rtsp}"
    return ip_or_host

def build_credentials(args: argparse.Namespace) -> List[Credential]:
    creds: List[Credential] = []

    # Credencial principal
    creds.append(Credential(label="user", username=args.user, password=args.passw))

    # Intento anónimo opcional
    if not args.no_anon:
        if args.user or args.passw:
            creds.append(Credential(label="anon", username="", password=""))

    # quitar duplicados
    uniq = {}
    for c in creds:
        uniq[(c.username, c.password)] = c
    return list(uniq.values())

def print_result(r: ProbeResult, verbose: bool) -> None:
    status = "OK" if r.ok else "FAIL"
    line = f"[{status:<4}] {r.protocol.upper():<4} {r.media_type:<6} [{r.credential_label:<4}] {r.endpoint_name} ({r.elapsed_ms} ms) -> {r.detail}"
    print(line)
    if verbose:
        print(f"       URL: {r.url}")
        if r.status_code is not None or r.content_type:
            print(f"       HTTP: status={r.status_code} ct={r.content_type}")

def save_csv(results: List[ProbeResult], path: str) -> None:
    fieldnames = list(asdict(results[0]).keys()) if results else [
        "endpoint_name","media_type","protocol","credential_label","url","ok","method_used",
        "status_code","content_type","detail","elapsed_ms"
    ]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow(asdict(r))

def main() -> int:
    args = parse_args()
    creds = build_credentials(args)

    print("=== Probe de streams IP Cam ===")
    print(f"Host base: {args.ip}")
    print(f"Credenciales a probar: {', '.join([c.label for c in creds])}")
    print(f"Timeout: {args.timeout}s")
    print(f"OpenCV: {'OK' if HAS_CV2 else 'NO'} | ffprobe: {'OK' if ffprobe_available() else 'NO'}")
    print("")

    results: List[ProbeResult] = []

    for endpoint in ENDPOINTS:
        name, media_type, protocol, _ = endpoint
        host = host_with_default_port(args.ip, protocol, args.port_http, args.port_rtsp)

        for cred in creds:
            result = probe_endpoint(
                host=host,
                endpoint=endpoint,
                cred=cred,
                channel=args.channel,
                timeout=args.timeout,
                http_basic_auth=args.http_basic_auth,
                embed_rtsp_auth=not args.no_embed_rtsp_auth,
            )
            results.append(result)

            if not args.only_success or result.ok:
                print_result(result, verbose=args.verbose)

    print("\n=== Resumen ===")
    ok_results = [r for r in results if r.ok]
    print(f"Total pruebas: {len(results)}")
    print(f"Éxitos: {len(ok_results)}")
    print(f"Fallos: {len(results) - len(ok_results)}")

    if ok_results:
        print("\nRutas válidas detectadas:")
        for r in ok_results:
            print(f" - [{r.protocol}] [{r.credential_label}] {r.endpoint_name}")
            print(f"   {r.url}")

    if args.csv:
        save_csv(results, args.csv)
        print(f"\nCSV guardado en: {args.csv}")

    return 0 if ok_results else 2


if __name__ == "__main__":
    sys.exit(main())