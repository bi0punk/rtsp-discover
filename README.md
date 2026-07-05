# RTSP Discover

Probe de cámaras IP que prueba 27+ endpoints HTTP/RTSP conocidos para detectar streams de video activos.

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-blue)](https://python.org)

## Tabla de Contenidos

- [Características](#características)
- [Stack](#stack)
- [Estructura](#estructura)
- [Requisitos](#requisitos)
- [Instalación](#instalación)
- [Uso](#uso)
- [Tests](#tests)
- [Configuración](#configuración)
- [CI](#ci)
- [Datos](#datos)
- [Limitaciones / Roadmap](#limitaciones--roadmap)
- [Licencia](#licencia)

## Características

- 27+ endpoints conocidos de cámaras IP (DAHUA, HIKVISION, ONVIF, genéricos, etc.)
- Placeholders `[USERNAME]`, `[PASSWORD]`, `[CHANNEL]` en las rutas
- Probes JPEG (snapshot), MJPEG (stream), RTSP (ffprobe + OpenCV), HTTP genérico
- Soporte para autenticación HTTP Basic Auth y credenciales embebidas en URL RTSP
- Timeout configurable por prueba
- Exportación de resultados a CSV
- Modo anónimo (prueba sin credenciales además de las proporcionadas)

## Stack

- **Python 3.11+**
- `requests` — peticiones HTTP
- `opencv-python` — captura de frames vía VideoCapture
- `ffprobe` (opcional, parte de ffmpeg) — detección de streams RTSP
- Linting: Ruff | Tests: pytest

## Estructura

```
rtsp-discover/
├── app.py                  # CLI principal
├── pyproject.toml          # Configuración del proyecto
├── requirements.txt        # requests, opencv-python
├── .env.example            # Variables de entorno de ejemplo
├── resultados_cam.csv      # Ejemplo de exportación CSV
├── tests/
│   └── test_smoke.py       # Tests de humo
├── .github/
│   └── workflows/
│       └── ci.yml          # CI: Ruff + pytest
├── LICENSE
└── README.md
```

## Requisitos

- Python >= 3.11
- `pip install requests opencv-python`
- Opcional: `ffprobe` (`sudo apt install ffmpeg`)

## Instalación

```bash
git clone https://github.com/tu-usuario/rtsp-discover.git
cd rtsp-discover
pip install -r requirements.txt
```

## Uso

```bash
python app.py --ip 192.168.1.100 --user admin --passw 12345 --timeout 5 --csv resultados.csv
```

### Argumentos

| Argumento | Default | Descripción |
|---|---|---|
| `--ip` | (requerido) | IP o host de la cámara |
| `--port-http` | 80 | Puerto HTTP |
| `--port-rtsp` | 554 | Puerto RTSP |
| `--user` | `""` | Usuario |
| `--passw` | `""` | Contraseña |
| `--channel` | 0 | Canal para endpoints [CHANNEL] |
| `--timeout` | 5 | Timeout por prueba (segundos) |
| `--http-basic-auth` | — | Probar HTTP Basic Auth |
| `--no-anon` | — | No probar acceso anónimo |
| `--only-success` | — | Mostrar solo resultados OK |
| `--csv` | `""` | Ruta para exportar CSV |
| `--verbose` | — | Mostrar URLs completas |

### Ejemplo de salida

```
=== Probe de streams IP Cam ===
Host base: 192.168.1.100
Credenciales a probar: user, anon
Timeout: 5s
OpenCV: OK | ffprobe: OK

[OK ] HTTP JPEG  [user] DAHAUS (312 ms) -> JPEG detectado por magic bytes
[OK ] RTSP FFMPEG[user] Gen 1 / Generic IP Cam (1240 ms) -> ffprobe detectó stream de video
[FAIL] HTTP MJPEG [anon] FOCUS 66 / HIDVCAM (5000 ms) -> No se detectó MJPEG

=== Resumen ===
Total pruebas: 54
Éxitos: 2
Fallos: 52

Rutas válidas detectadas:
 - [http] [user] DAHAUS
   http://192.168.1.100/cgi-bin/snapshot.cgi?chn=0&u=admin&p=12345
 - [rtsp] [user] Gen 1 / Generic IP Cam
   rtsp://admin:12345@192.168.1.100:554/live/ch00_0
```

## Tests

```bash
pip install pytest
python -m pytest tests/ -v
```

## Configuración

Variables de entorno (`.env.example`):

```env
TARGET_IP=192.168.1.100
USERNAME=admin
PASSWORD=your_password
TIMEOUT=5
OUTPUT_CSV=resultados_cam.csv
```

## CI

GitHub Actions ejecuta Ruff linting y pytest en cada push y pull request:

```yaml
- name: Ruff check
  run: uv run ruff check .
- name: Pytest
  run: uv run pytest -q
```

## Datos

El archivo `resultados_cam.csv` contiene un ejemplo del formato de exportación con los campos: `endpoint_name`, `media_type`, `protocol`, `credential_label`, `url`, `ok`, `method_used`, `status_code`, `content_type`, `detail`, `elapsed_ms`.

## Limitaciones / Roadmap

- No soporta autenticación digest (solo Basic Auth y credenciales en URL)
- Depende de ffprobe para detección óptima de RTSP (fallback a OpenCV)
- No realiza escaneo de puertos — requiere conocer los puertos HTTP/RTSP
- Los endpoints son estáticos; no hay descubrimiento ONVIF automático
- Futuro: escaneo de puertos, autenticación digest, descubrimiento ONVIF WS-Discovery, soporte para RTSP over TCP/TLS, paralelización de pruebas

## Licencia

MIT
