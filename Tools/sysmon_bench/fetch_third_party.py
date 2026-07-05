"""Fetch third-party pure-Python projects used as large coverage sets.

Downloads sdists from PyPI into Tools/sysmon_bench/third_party/ (which is
gitignored) and extracts them.  Uses curl so that proxy/CA configuration
from the environment applies.
"""

import os
import subprocess
import sys
import tarfile

HERE = os.path.dirname(os.path.abspath(__file__))
THIRD_PARTY = os.path.join(HERE, "third_party")

PACKAGES = [
    (
        "pygments-2.19.2",
        "https://files.pythonhosted.org/packages/source/p/pygments/pygments-2.19.2.tar.gz",
    ),
]


def main():
    os.makedirs(THIRD_PARTY, exist_ok=True)
    for name, url in PACKAGES:
        dest = os.path.join(THIRD_PARTY, name)
        if os.path.isdir(dest):
            print(f"{name}: already present")
            continue
        tgz = os.path.join(THIRD_PARTY, name + ".tar.gz")
        print(f"fetching {url}")
        subprocess.run(["curl", "-sSL", "-o", tgz, url], check=True)
        with tarfile.open(tgz) as tf:
            tf.extractall(THIRD_PARTY, filter="data")
        os.unlink(tgz)
        found = [d for d in os.listdir(THIRD_PARTY) if d.lower() == name.lower()]
        print(f"{name}: extracted -> {found}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
