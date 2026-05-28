import os
import logging
import httpx
import ipaddress
import maxminddb
import threading
from functools import lru_cache

logger = logging.getLogger(__name__)

DB_URL = "https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-City.mmdb"
DB_PATH = "GeoLite2-City.mmdb"

_reader = None
_reader_lock = threading.Lock()


def _global_ip_or_none(ip_address: str):
    try:
        ip = ipaddress.ip_address(str(ip_address).strip())
    except ValueError:
        return None
    if not ip.is_global:
        return None
    return str(ip)

async def download_geoip_db_if_missing():
    """Download the GeoLite2 City database if it doesn't exist."""
    global _reader
    if not os.path.exists(DB_PATH):
        logger.info(f"Downloading GeoIP database from {DB_URL} (this may take a minute)...")
        try:
            timeout = httpx.Timeout(180.0, connect=20.0)
            tmp_path = f"{DB_PATH}.part"
            async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
                async with client.stream("GET", DB_URL) as response:
                    response.raise_for_status()
                    with open(tmp_path, "wb") as f:
                        async for chunk in response.aiter_bytes():
                            f.write(chunk)
            os.replace(tmp_path, DB_PATH)
            logger.info("GeoIP database downloaded successfully.")
        except Exception as e:
            logger.error(f"Failed to download GeoIP database: {e}")
            return

    # Initialize reader
    try:
        _reader = maxminddb.open_database(DB_PATH)
        logger.info("GeoIP database loaded successfully.")
    except Exception as e:
        logger.error(f"Failed to load GeoIP database: {e}")

@lru_cache(maxsize=int(os.getenv("GEOIP_CACHE_SIZE", "10000")))
def _lookup_location_data(ip_address: str) -> tuple[tuple[str, str], ...]:
    with _reader_lock:
        if not _reader:
            return ()
        try:
            data = _reader.get(ip_address)
        except Exception as e:
            logger.warning(f"GeoIP lookup failed for IP {ip_address}: {e}")
            return ()

    if not data:
        return ()

    loc = {}

    # City
    if 'city' in data and 'names' in data['city'] and 'en' in data['city']['names']:
        loc['ct'] = data['city']['names']['en']

    # State/Region
    if 'subdivisions' in data and len(data['subdivisions']) > 0:
        sub = data['subdivisions'][0]
        if 'iso_code' in sub:
            loc['st'] = sub['iso_code']
        elif 'names' in sub and 'en' in sub['names']:
            loc['st'] = sub['names']['en']

    # Country
    if 'country' in data and 'iso_code' in data['country']:
        loc['country'] = data['country']['iso_code'].lower()

    # Zip Code
    if 'postal' in data and 'code' in data['postal']:
        loc['zp'] = data['postal']['code']

    return tuple(loc.items())


def get_location_data(ip_address: str) -> dict:
    """
    Get city, state, country, and zip code from IP address.
    Returns a dict with 'ct', 'st', 'country', 'zp' keys.
    """
    if not ip_address:
        return {}

    global_ip = _global_ip_or_none(ip_address)
    if not global_ip:
        return {}

    return dict(_lookup_location_data(global_ip))

def close_geoip_db():
    global _reader
    with _reader_lock:
        if _reader:
            try:
                _reader.close()
            except Exception:
                pass
            _reader = None
    _lookup_location_data.cache_clear()
