"""Update the dependencies for a homebrew formula.

Run with the path to the formula as the first argument.
"""

import json
from pathlib import Path
import sys
import re
from urllib.request import urlopen
import subprocess
import shutil

if len(sys.argv) != 2:
    print(__doc__)
    print()
    print("Usage: update-python-homebrew-formula.py <formula>")
    exit(1)

formula = Path(sys.argv[1])
content = formula.read_text()

URL_HAS_REGEX = re.compile(r"(?P<l1>url\s+)[\"\'](?P<url>[^\"\']+)[\"\'](?P<l2>\s+sha256\s+)[\"\'](?P<sha256>[^\'\"]+)[\"\']", re.MULTILINE)

def get_package_from_url(url):
    """Return the package name from a url on PyPI."""
    return normalize_package_name(url.rsplit("/", 1)[-1].split(".", 1)[0].rsplit("-", 1)[0])

def get_metadata(package_name, version = None):
    """Get the metadata for a package from PyPI."""
    metadata_url = f"https://pypi.python.org/pypi/{package_name}/json"
    response = urlopen(metadata_url)
    metadata = json.loads(response.read().decode("utf-8"))
    release = metadata["releases"][version] if version is not None else metadata["urls"]
    tar_urls = [url for url in release if url["filename"].endswith(".tar.gz")]
    metadata["tar"] = None if not tar_urls else tar_urls[0]
    return metadata

def normalize_package_name(package):
    """We need them to match."""
    return package.replace("-", "_")

for match in URL_HAS_REGEX.finditer(content):
    local_root_url = match.group("url")
    local_root_sha256 = match.group("sha256")
    root_package = get_package_from_url(local_root_url)
    print(root_package)
    break
root_meta = get_metadata(root_package)
if not root_meta["tar"]:
    print("ERROR: Could not find tar.gz url")
    exit(1)
tar_url = root_meta["tar"]
latest_root_sha256 = tar_url["digests"]["sha256"]
latest_root_url = tar_url["url"]
if local_root_sha256 == latest_root_sha256:
    print("\talready up to date")
    exit(0)
print("Updating", root_package)
content = content.replace(local_root_sha256, latest_root_sha256)
content = content.replace(local_root_url, latest_root_url)
print("creating venv")
VEVNV = ".venv"
shutil.rmtree(VEVNV, ignore_errors=True)
subprocess.check_call(["python3", "-m", "venv", VEVNV])

print("installing dependencies")
subprocess.check_call([f"{VEVNV}/bin/python", "-m", "pip", "install", tar_url["url"]])

print("getting updated versions")
freeze = subprocess.check_output([f"{VEVNV}/bin/python", "-m", "pip", "freeze", "--local"], encoding="utf-8")
dependencies = {
    normalize_package_name(line.strip().split("==")[0].strip()): line.strip().split("==")[1].strip()
    for line in freeze.splitlines()
    if "==" in line # excludes root package
}

pypi_versions = {} # package: sha256, url
local_versions = {} # package: sha256, url

for match in URL_HAS_REGEX.finditer(content):
    local_root_url = match.group("url")
    local_root_sha256 = match.group("sha256")
    package = get_package_from_url(local_root_url)
    local_versions[package] = (local_root_sha256, local_root_url)

for package, version in dependencies.items():
    meta = get_metadata(package, version)
    pypi_versions[package] = (meta["tar"]["digests"]["sha256"], meta["tar"]["url"])

add = ""
print("updating dependencies")
for package, (pypi_sha256, pypi_url) in pypi_versions.items():
    if package not in local_versions:
        print(f"Adding {package}")
        add += f"""
  resource "{package}" do
    url "{pypi_url}"
    sha256 "{pypi_sha256}"
  end
"""
        continue

    local_root_sha256, local_url = local_versions[package]
    if pypi_sha256 == local_root_sha256:
        print(f"\t{package} already up to date")
        continue

    print(f"Updating {package}")
    content = content.replace(local_root_sha256, pypi_sha256)
    content = content.replace(local_url, pypi_url)

content_with_added_packages = content[:content.rfind("end")] + add + content[content.rfind("end"):]

formula.write_text(content_with_added_packages)
