# rtsp-discover

Probe IP cameras via HTTP/RTSP to detect active video streams. Tests 27+ known camera endpoint patterns against a given host, supporting JPEG snapshots, MJPEG, RTSP, and HTTP video streams.

## Stack

Python 3.10+, OpenCV, ffprobe

## Usage

```bash
pip install opencv-python
python app.py <target_ip>
```

## Features

- 27+ known camera endpoint patterns
- Credential/placeholder injection (`[USERNAME]`, `[PASSWORD]`, `[CHANNEL]`)
- JPEG snapshot, MJPEG stream, RTSP probe
- Configurable timeouts
- CSV export of results
- Anonymous access option

## License

MIT
