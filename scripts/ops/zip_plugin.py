"""Build the distributable Buykori AdSync WordPress plugin ZIP.

The ZIP must contain exactly one top-level folder named `buykori-adsync`.
Only runtime plugin files are packaged; local build/test artifacts are skipped.
"""

from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_SLUG = "buykori-adsync"
SOURCE_DIR = PROJECT_ROOT / "wordpress-plugin" / PLUGIN_SLUG
OUTPUT_ZIP = PROJECT_ROOT / "wordpress-plugin" / f"{PLUGIN_SLUG}.zip"
FIXED_ZIP_DATE = (2026, 1, 1, 0, 0, 0)

EXCLUDED_NAMES = {
    ".DS_Store",
    "Thumbs.db",
}
EXCLUDED_SUFFIXES = {
    ".bak",
    ".log",
    ".map",
    ".orig",
    ".pyc",
    ".swp",
    ".tmp",
    ".zip",
}
EXCLUDED_PARTS = {
    ".git",
    "__MACOSX",
    "__pycache__",
    "node_modules",
}


def should_include(path: Path) -> bool:
    parts = set(path.parts)
    if parts & EXCLUDED_PARTS:
        return False
    if path.name in EXCLUDED_NAMES:
        return False
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    return path.is_file()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def extract_version() -> str:
    main_file = SOURCE_DIR / f"{PLUGIN_SLUG}.php"
    readme = SOURCE_DIR / "readme.txt"
    main_text = read_text(main_file)
    readme_text = read_text(readme)

    header_match = re.search(r"^\s*\*\s*Version:\s*([0-9A-Za-z.\-_]+)\s*$", main_text, re.MULTILINE)
    const_match = re.search(r"define\(\s*'BUYKORIGW_VERSION'\s*,\s*'([^']+)'\s*\)", main_text)
    stable_match = re.search(r"^Stable tag:\s*([0-9A-Za-z.\-_]+)\s*$", readme_text, re.MULTILINE)

    versions = {
        "plugin header": header_match.group(1) if header_match else "",
        "BUYKORIGW_VERSION": const_match.group(1) if const_match else "",
        "readme Stable tag": stable_match.group(1) if stable_match else "",
    }
    missing = [name for name, version in versions.items() if not version]
    if missing:
        raise RuntimeError(f"Missing version metadata: {', '.join(missing)}")
    if len(set(versions.values())) != 1:
        raise RuntimeError(f"Version mismatch: {versions}")
    return next(iter(versions.values()))


def validate_source() -> None:
    required = [
        SOURCE_DIR / f"{PLUGIN_SLUG}.php",
        SOURCE_DIR / "readme.txt",
        SOURCE_DIR / "uninstall.php",
        SOURCE_DIR / "includes" / "auto-updater.php",
    ]
    missing = [str(path.relative_to(PROJECT_ROOT)) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"Missing required plugin files: {', '.join(missing)}")


def build_zip() -> tuple[int, str]:
    files = sorted(path for path in SOURCE_DIR.rglob("*") if should_include(path))
    if not files:
        raise RuntimeError("No plugin files found to package")

    OUTPUT_ZIP.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT_ZIP.exists():
        OUTPUT_ZIP.unlink()

    with zipfile.ZipFile(OUTPUT_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            relative = path.relative_to(SOURCE_DIR)
            archive_name = f"{PLUGIN_SLUG}/{relative.as_posix()}"
            info = zipfile.ZipInfo(archive_name, FIXED_ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())

    package_hash = hashlib.sha256(OUTPUT_ZIP.read_bytes()).hexdigest()
    return len(files), package_hash


def validate_zip(expected_version: str) -> None:
    with zipfile.ZipFile(OUTPUT_ZIP) as archive:
        names = archive.namelist()
        if not names:
            raise RuntimeError("ZIP is empty")
        top_levels = {name.split("/", 1)[0] for name in names}
        if top_levels != {PLUGIN_SLUG}:
            raise RuntimeError(f"Unexpected ZIP top-level entries: {sorted(top_levels)}")
        main_name = f"{PLUGIN_SLUG}/{PLUGIN_SLUG}.php"
        if main_name not in names:
            raise RuntimeError(f"Missing plugin entry file in ZIP: {main_name}")
        bad = [
            name for name in names
            if name.startswith(".")
            or "/." in name
            or "__MACOSX" in name
            or "__pycache__" in name
            or name.endswith(".pyc")
            or name.endswith(".zip")
        ]
        if bad:
            raise RuntimeError(f"Unexpected artifact files in ZIP: {bad}")
        main_text = archive.read(main_name).decode("utf-8")
        if f"Version:           {expected_version}" not in main_text:
            raise RuntimeError("Packaged plugin header version did not match source version")


def main() -> int:
    validate_source()
    version = extract_version()
    file_count, package_hash = build_zip()
    validate_zip(version)
    print(f"Built {OUTPUT_ZIP.relative_to(PROJECT_ROOT)}")
    print(f"Version: {version}")
    print(f"Files: {file_count}")
    print(f"SHA256: {package_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
