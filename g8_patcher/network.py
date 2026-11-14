"""Fetch the one supported original from its publisher, without a mirror."""
from __future__ import annotations

import hashlib
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .core import PatcherError, SOURCE, validate_source


def _check_url(url: str) -> None:
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise PatcherError("Official firmware server returned an invalid redirect URL.") from error
    if (parsed.scheme != "https" or parsed.hostname != "ota.xiaoji.com"
            or port not in (None, 443) or parsed.username is not None
            or parsed.password is not None):
        raise PatcherError("Download redirect left the official HTTPS firmware server.")


class _OfficialRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_original(destination_dir: Path) -> Path:
    """Return a verified cached/new original; never replace an existing file."""
    url = SOURCE["url"]
    _check_url(url)
    destination_dir = Path(destination_dir).expanduser().resolve()
    filename = Path(urllib.parse.urlsplit(url).path).name
    destination = destination_dir / filename
    if destination.is_symlink():
        raise PatcherError("The original download destination is a symbolic link.")
    if destination.exists():
        validate_source(destination)
        return destination

    request = urllib.request.Request(url, headers={
        "User-Agent": "G8-Compat-Patcher/0.1.1",
        "Accept": "application/zip",
    })
    opener = urllib.request.build_opener(_OfficialRedirects())
    try:
        with opener.open(request, timeout=20) as response:
            _check_url(response.url)
            if response.status != 200:
                raise PatcherError(f"Official server returned HTTP {response.status}.")
            data = response.read(SOURCE["zipBytes"] + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise PatcherError(
            "Official firmware download failed. Retry later or choose a previously "
            "saved supported original ZIP. " + str(error)
        ) from error
    if (len(data) != SOURCE["zipBytes"]
            or hashlib.sha256(data).hexdigest() != SOURCE["zipSha256"]):
        raise PatcherError("Official download differs from the supported original; no patch was applied.")

    created = False
    try:
        destination_dir.mkdir(parents=True, exist_ok=True)
        # Exclusive creation also rejects a file created while the GET was running.
        with destination.open("xb") as stream:
            created = True
            stream.write(data)
        validate_source(destination)
    except (OSError, PatcherError) as error:
        cleanup = ""
        if created:
            try:
                destination.unlink()
            except OSError as cleanup_error:
                cleanup = f" Partial download remains at {destination}: {cleanup_error}"
        raise PatcherError("Cannot save and verify original: " + str(error) + cleanup) from error
    return destination
