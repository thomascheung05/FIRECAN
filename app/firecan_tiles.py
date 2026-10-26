"""Versioned local map artifacts. No tile generation occurs in a web worker."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path

TILE_ROOT = Path(__file__).resolve().parents[1] / 'data' / 'tiles'
TILE_ATTRIBUTES = ('province', 'fire_year', 'fire_size', 'data_source', 'data_aquisition')


def file_identity(path):
    stat = Path(path).stat()
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


@lru_cache(maxsize=16)
def _fingerprint(path, identity):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(chunk)
    if file_identity(path) != identity:
        raise ValueError('Dataset changed while reading it. Restart after replacing matched artifacts.')
    return {'sha256': digest.hexdigest(), 'size': identity[2]}


def fingerprint(path):
    return _fingerprint(str(Path(path).resolve()), file_identity(path)).copy()


def dataset_sources(full_path, display_path):
    return {'original': fingerprint(full_path), 'display': fingerprint(display_path)}


def dataset_version(sources):
    return hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest()


def read_manifest(root=TILE_ROOT):
    try:
        manifest = json.loads((Path(root) / 'manifest.json').read_text())
    except FileNotFoundError as exc:
        raise ValueError('Tile manifest is missing. Run scripts/build_tiles.py and reload the page.') from exc
    version = manifest['dataset_version']
    if len(version) != 64 or any(c not in '0123456789abcdef' for c in version):
        raise ValueError('Invalid tile dataset version.')
    if dataset_version(manifest['sources']) != version:
        raise ValueError('Invalid tile manifest fingerprints.')
    archive = Path(root) / version / 'fires.pmtiles'
    if not archive.is_file() or archive.stat().st_size != manifest['archive_size']:
        raise ValueError('Tile archive is missing or incomplete. Run scripts/build_tiles.py.')
    return manifest, archive


def compact_selection(ids, total):
    ids = sorted(int(i) for i in ids)
    if not ids:
        return {'mode': 'include', 'ids': []}
    if len(ids) == total:
        return {'mode': 'all', 'ids': []}
    if len(ids) <= total // 2:
        return {'mode': 'include', 'ids': ids}
    selected = set(ids)
    return {'mode': 'exclude', 'ids': [i for i in range(total) if i not in selected]}
