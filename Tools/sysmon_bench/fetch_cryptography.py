"""Fetch pyca/cryptography (wheel + sdist tests) and coverage.py for the
pytest-suite benchmark.

Installs into Tools/sysmon_bench/third_party/ (gitignored):
  pylibs/            pip --target with pytest, coverage (compiled C tracer),
                     cryptography (abi3 wheel), cryptography_vectors, pretend
  cryptography-X.Y/  sdist tree providing tests/
  coverage-patched/  coverage source tree with sysmon fixes applied
                     (see RESULTS.md "coverage.py-side findings")

The abi3 cryptography wheel (built for cp311+) loads on this 3.16 build via
the stable ABI, letting us run its test suite without a Rust toolchain.
"""

import os
import subprocess
import sys
import tarfile

HERE = os.path.dirname(os.path.abspath(__file__))
THIRD_PARTY = os.path.join(HERE, "third_party")
PYLIBS = os.path.join(THIRD_PARTY, "pylibs")

CRYPTOGRAPHY_VERSION = "45.0.5"
COVERAGE_VERSION = "7.10.0"


def pip(*args):
    subprocess.run(
        [sys.executable, "-m", "pip", *args],
        check=True,
    )


def main():
    os.makedirs(THIRD_PARTY, exist_ok=True)

    # Runtime deps into pylibs (abi3 wheel for cryptography; coverage from
    # sdist so its C tracer is compiled for this interpreter).
    pip(
        "install", "--target", PYLIBS, "--upgrade",
        "pytest", "pretend", "certifi",
        f"cryptography=={CRYPTOGRAPHY_VERSION}",
        f"cryptography_vectors=={CRYPTOGRAPHY_VERSION}",
        "--no-warn-script-location",
    )
    pip(
        "install", "--target", PYLIBS, "--upgrade", "--no-binary", "coverage",
        f"coverage=={COVERAGE_VERSION}",
        "--no-warn-script-location",
    )

    # Tests come from the sdist.
    sdist_name = f"cryptography-{CRYPTOGRAPHY_VERSION}"
    dest = os.path.join(THIRD_PARTY, sdist_name)
    if not os.path.isdir(dest):
        tgz = os.path.join(THIRD_PARTY, sdist_name + ".tar.gz")
        url = (
            "https://files.pythonhosted.org/packages/source/c/cryptography/"
            f"{sdist_name}.tar.gz"
        )
        subprocess.run(["curl", "-sSL", "-o", tgz, url], check=True)
        with tarfile.open(tgz) as tf:
            tf.extractall(THIRD_PARTY, filter="data")
        os.unlink(tgz)

    # Patched coverage: copy the pure-Python tree and apply the sysmon fixes.
    patched = os.path.join(THIRD_PARTY, "coverage-patched")
    if not os.path.isdir(patched):
        cov_sdist = f"coverage-{COVERAGE_VERSION}"
        tgz = os.path.join(THIRD_PARTY, cov_sdist + ".tar.gz")
        url = (
            "https://files.pythonhosted.org/packages/source/c/coverage/"
            f"{cov_sdist}.tar.gz"
        )
        subprocess.run(["curl", "-sSL", "-o", tgz, url], check=True)
        with tarfile.open(tgz) as tf:
            tf.extractall(THIRD_PARTY, filter="data")
        os.unlink(tgz)
        os.makedirs(patched)
        os.rename(
            os.path.join(THIRD_PARTY, cov_sdist, "coverage"),
            os.path.join(patched, "coverage"),
        )
        patch_path = os.path.join(HERE, "coverage-sysmon.patch")
        subprocess.run(
            ["patch", "-p1", "-d", patched, "-i", patch_path], check=True
        )

    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
