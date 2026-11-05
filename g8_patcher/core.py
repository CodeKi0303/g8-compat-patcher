"""Pinned, local-only firmware transformation; no device access or flashing."""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import re
import uuid
import zipfile


class PatcherError(Exception):
    """An expected input, validation, or output failure safe to show to a user."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_catalog() -> tuple[dict, dict[str, dict]]:
    try:
        catalog = json.loads(Path(__file__).with_name("profiles.json").read_text("utf-8"))
        if catalog["schemaVersion"] != 1:
            raise ValueError("unsupported schema")
        source = catalog["source"]
        if not isinstance(source["zipBytes"], int) or source["zipBytes"] <= 0:
            raise ValueError("invalid ZIP size")
        if not isinstance(source["mainBytes"], int) or source["mainBytes"] <= 0:
            raise ValueError("invalid firmware size")
        for field in ("zipSha256", "mainSha256"):
            if not re.fullmatch(r"[a-f0-9]{64}", source[field]):
                raise ValueError("invalid digest")
        members = source["members"]
        if (not isinstance(members, list) or not members
                or len({m["name"] for m in members}) != len(members)
                or any(not isinstance(m["bytes"], int) or m["bytes"] <= 0 for m in members)
                or {m["name"]: m["bytes"] for m in members}.get(source["mainMember"]) != source["mainBytes"]):
            raise ValueError("invalid ZIP members")
        profiles: dict[str, dict] = {}
        for profile in catalog["profiles"]:
            identifier = profile["id"]
            if not re.fullmatch(r"[a-z0-9-]+", identifier) or identifier in profiles:
                raise ValueError("invalid or duplicate profile")
            if not re.fullmatch(r"[a-f0-9]{64}", profile["outputSha256"]):
                raise ValueError("invalid output digest")
            if not re.fullmatch(r"129\.\d+-1\.5", profile["packageSelectionVersion"]):
                raise ValueError("invalid package selection version")
            if not isinstance(profile["label"], str) or not isinstance(profile["description"], str):
                raise ValueError("invalid profile text")
            previous_end = 0
            if not profile["changes"]:
                raise ValueError("empty patch")
            for change in profile["changes"]:
                offset = change["offset"]
                replacement = bytes.fromhex(change["replacementHex"])
                if (type(offset) is not int or offset < previous_end or not replacement
                        or offset + len(replacement) > source["mainBytes"]):
                    raise ValueError("patch overlaps or exceeds the image")
                previous_end = offset + len(replacement)
            profiles[identifier] = profile
        if not profiles:
            raise ValueError("no profiles")
        return source, profiles
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise PatcherError(f"Patch definitions are missing or invalid: {error}") from error


_SOURCE, _PROFILES = _load_catalog()
# Public download metadata is a copy: callers cannot change validation state.
SOURCE = copy.deepcopy(_SOURCE)


def list_profiles() -> list[dict]:
    """Return display metadata without exposing mutable internal definitions."""
    return [{key: copy.deepcopy(value) for key, value in profile.items() if key != "changes"}
            for profile in _PROFILES.values()]


def validate_source(source_zip: Path) -> bytes:
    """Read one exact official ZIP and return its validated Main image.

    The archive digest is checked before ZIP metadata or compressed data is read.
    Repacked archives and any other G8 version are intentionally rejected.
    """
    source_zip = Path(source_zip)
    try:
        with source_zip.open("rb") as stream:
            data = stream.read(_SOURCE["zipBytes"] + 1)
    except OSError as error:
        raise PatcherError(f"Cannot read original ZIP: {error}") from error
    if len(data) != _SOURCE["zipBytes"] or _sha256(data) != _SOURCE["zipSha256"]:
        raise PatcherError("Original ZIP does not match the supported official G8 129.60-1.5 file. "
                           "Use the official download or an unchanged copy of that exact ZIP.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            expected = {member["name"]: member["bytes"] for member in _SOURCE["members"]}
            entries = archive.infolist()
            if len(entries) != len(expected) or {e.filename for e in entries} != set(expected):
                raise PatcherError("Original ZIP member list differs from the verified release.")
            payloads = {}
            for entry in entries:
                if (entry.file_size != expected[entry.filename] or entry.flag_bits & 1
                        or entry.is_dir() or entry.compress_size > len(data)):
                    raise PatcherError("Original ZIP member metadata differs from the verified release.")
                with archive.open(entry) as stream:
                    member = stream.read(expected[entry.filename] + 1)
                if len(member) != expected[entry.filename]:
                    raise PatcherError("Original ZIP contains an unexpected expanded file size.")
                payloads[entry.filename] = member
            main = payloads[_SOURCE["mainMember"]]
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, NotImplementedError) as error:
        raise PatcherError(f"Original ZIP could not be validated: {error}") from error
    if len(main) != _SOURCE["mainBytes"] or _sha256(main) != _SOURCE["mainSha256"]:
        raise PatcherError("Original Main firmware does not match the verified release.")
    return main


def _patch(original: bytes, profile: dict) -> bytes:
    if len(original) != _SOURCE["mainBytes"] or _sha256(original) != _SOURCE["mainSha256"]:
        raise PatcherError("Patch input is not the verified original Main firmware.")
    patched = bytearray(original)
    for change in profile["changes"]:
        offset, replacement = change["offset"], bytes.fromhex(change["replacementHex"])
        if any(a == b for a, b in zip(original[offset:offset + len(replacement)], replacement)):
            raise PatcherError("Patch definition includes unchanged source bytes.")
        patched[offset:offset + len(replacement)] = replacement
    result = bytes(patched)
    if len(result) != len(original) or _sha256(result) != profile["outputSha256"]:
        raise PatcherError("Generated firmware does not match the previously verified firmware hash.")
    return result


def _archive_bytes(main: bytes) -> bytes:
    target = io.BytesIO()
    # Fixed metadata makes repeated builds reproducible. The outer filename stays
    # unique because GameSir may reuse an extraction directory with the same stem.
    entry = zipfile.ZipInfo("G6C_ISP.bin", date_time=(2024, 3, 1, 0, 0, 0))
    entry.create_system = 3
    entry.external_attr = 0o100644 << 16
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr(entry, main, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    data = target.getvalue()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if (archive.namelist() != ["G6C_ISP.bin"] or archive.testzip() is not None
                or archive.read("G6C_ISP.bin") != main):
            raise PatcherError("Generated ZIP did not pass payload and CRC verification.")
    return data


def build_package(source_zip: Path, output_dir: Path, profile_id: str = "kishi-xbox") -> dict:
    """Create a fresh Main-only ZIP and a public-safe verification report.

    The selected directory receives a unique subdirectory. No existing files,
    source archive, device, or controller state are modified.
    """
    if profile_id not in _PROFILES:
        raise PatcherError(f"Unknown profile: {profile_id}")
    profile = _PROFILES[profile_id]
    original = validate_source(source_zip)
    main = _patch(original, profile)
    archive_data = _archive_bytes(main)
    now = dt.datetime.now(dt.timezone.utc)
    tag = f"g8-{profile_id}-{now:%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex}"
    filename = f"{tag}_gamesir-g8_firmware_{profile['packageSelectionVersion']}.zip"
    record = {
        "schemaVersion": 1,
        "createdAtUtc": now.isoformat(),
        "profile": profile_id,
        "source": {key: _SOURCE[key] for key in ("url", "zipBytes", "zipSha256", "mainBytes", "mainSha256")},
        "output": {"archive": filename, "archiveBytes": len(archive_data),
                   "archiveSha256": _sha256(archive_data), "mainMember": "G6C_ISP.bin",
                   "mainBytes": len(main), "mainSha256": _sha256(main)},
        "versions": {"internalFirmwareRelease": "129.60-1.5", "versionBytesChanged": False,
                     "packageSelectionVersion": profile["packageSelectionVersion"],
                     "packageSelectionVersionIsOfficialRelease": False},
        "verification": {"exactOriginalZip": True, "exactOriginalMain": True,
                         "matchesPreviouslyVerifiedMainSha256": True,
                         "zipCrcAndPayloadPassed": True,
                         "changedBytes": sum(a != b for a, b in zip(original, main))},
        "scope": "Local Main image generation only. Left and PD are not included. "
                 "No controller readback or flashing is performed. Xbox profile retains PS USB HID format.",
    }
    report_data = (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    try:
        parent = Path(output_dir).resolve()
        parent.mkdir(parents=True, exist_ok=True)
        job = parent / tag
        job.mkdir()
    except OSError as error:
        raise PatcherError(f"Cannot create a new output directory: {error}") from error
    archive_path, report_path = job / filename, job / "verification.json"
    owned: list[Path] = []
    try:
        for path, data in ((archive_path, archive_data), (report_path, report_data)):
            with path.open("xb") as stream:
                owned.append(path)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            if path.read_bytes() != data:
                raise PatcherError("Output readback does not match generated bytes.")
    except (OSError, PatcherError) as error:
        failures = []
        for path in reversed(owned):
            try:
                path.unlink()
            except OSError as cleanup_error:
                failures.append(str(cleanup_error))
        try:
            job.rmdir()
        except OSError as cleanup_error:
            failures.append(str(cleanup_error))
        suffix = f" Partial output remains at {job}: {'; '.join(failures)}" if failures else ""
        raise PatcherError(f"Cannot finish writing the package: {error}.{suffix}") from error
    return {"archive": str(archive_path), "report": str(report_path), "profile": profile_id,
            "main_sha256": _sha256(main), "archive_sha256": _sha256(archive_data),
            "main_bytes": len(main)}
