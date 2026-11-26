"""Synchronize folder removals with the catalog at launcher start and workbench focus."""
from file_lock import FileLock
from import_packages import DIRECTORY
from imported_package_uninstall import refresh_packages


def synchronize(root, addon):
    location = addon / DIRECTORY
    try:
        result = refresh_packages(root, addon, lock_factory=FileLock)
    except (OSError, ValueError, TimeoutError) as exc:
        result = {'removed': [], 'blocked': [{'directory': DIRECTORY, 'error': str(exc)}]}
    return dict(result, location=str(location))
