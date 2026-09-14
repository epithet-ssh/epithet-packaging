#!/usr/bin/env python3
"""Publish locally built artifacts after verifying their release receipts.

The shell scripts own execution. This helper owns archive validation, signing,
immutable files, and atomic metadata updates. No forge APIs are involved.
"""
import argparse
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.parse

from metadata import read_release, sha256, verify, version

LOG = logging.getLogger("publisher")
ROOT = Path(__file__).resolve().parent.parent


def run(*args, **kwargs):
    LOG.info("running %s", " ".join(map(str, args)))
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def switch(link, target):
    """Replace a relative symlink atomically, on its own filesystem."""
    temporary = link.with_name(f".{link.name}.{os.getpid()}")
    try:
        temporary.symlink_to(target)
        os.replace(temporary, link)
    finally:
        temporary.unlink(missing_ok=True)


def current_arch(root):
    path = root / "current/manifest.json"
    return json.loads(path.read_text())["tag"] if path.exists() else None


def should_publish(current, proposed):
    return current is None or version(current) < version(proposed)


def inspect_index(path, manifest, files=False):
    """Validate the sole package record without extracting untrusted paths."""
    prefix = f"epithet-{manifest['tag'][1:]}-1"
    expected = {f"{prefix}/desc"}
    if files:
        expected.add(f"{prefix}/files")
    with tarfile.open(path, "r:gz") as archive:
        names = set()
        desc = None
        for member in archive.getmembers():
            if member.isdir() and member.name.rstrip("/") == prefix:
                continue
            if not member.isfile() or member.name not in expected or member.name in names or member.size > 1024 * 1024:
                raise ValueError(f"unexpected repository entry: {member.name}")
            names.add(member.name)
            if member.name.endswith("/desc"):
                desc = archive.extractfile(member).read().decode()
        if names != expected:
            raise ValueError("repository index is incomplete")
    fields = {}
    for block in desc.strip().split("\n\n"):
        lines = block.splitlines()
        if lines[0] in fields:
            raise ValueError("duplicate repository field")
        fields[lines[0]] = lines[1:]
    required = {"%NAME%": "epithet", "%VERSION%": manifest["tag"][1:] + "-1",
                "%ARCH%": "x86_64", "%FILENAME%": f"epithet-{manifest['tag'][1:]}-1-x86_64.pkg.tar.zst",
                "%SHA256SUM%": manifest["assets"][f"epithet-{manifest['tag'][1:]}-1-x86_64.pkg.tar.zst"]}
    if any(fields.get(key) != [value] for key, value in required.items()):
        raise ValueError("repository index does not describe the expected package")


def sign(config, path):
    fingerprint = config["arch_key_fingerprint"]
    if not re.fullmatch(r"[A-Fa-f0-9]{40}|[A-Fa-f0-9]{64}", fingerprint):
        raise ValueError("arch_key_fingerprint must be a full OpenPGP fingerprint")
    signature = Path(str(path) + ".sig")
    args = ["gpg", "--batch", "--homedir", config["arch_gnupg_home"]]
    run(*args, "--local-user", fingerprint, "--output", signature, "--detach-sign", path)
    run(*args, "--verify", signature, path)


def immutable_copy(source, target):
    """Never overwrite a package filename; expose a new file only when complete."""
    if target.exists():
        if sha256(source) != sha256(target):
            raise ValueError(f"immutable file already exists with different bytes: {target}")
        return
    # Both are on PUBLIC_ROOT's filesystem. link(2) creates a complete file and
    # refuses replacement even if another process races this operation.
    os.link(source, target)


def publish_arch(config, manifest, work):
    root = Path(config["public_root"]) / "arch/x86_64"
    root.mkdir(parents=True, exist_ok=True)
    if not should_publish(current_arch(root), manifest["tag"]):
        LOG.info("Arch is already at %s or newer", manifest["tag"])
        return
    inspect_index(work / "epithet.db.tar.gz", manifest)
    inspect_index(work / "epithet.files.tar.gz", manifest, files=True)
    # Stage beneath the public root to keep hard links and promotion on one FS.
    with tempfile.TemporaryDirectory(prefix=".stage-", dir=root) as staging:
        stage = Path(staging)
        stage.chmod(0o755)
        package = f"epithet-{manifest['tag'][1:]}-1-x86_64.pkg.tar.zst"
        for name in manifest["assets"]:
            shutil.copyfile(work / name, stage / name)
            (stage / name).chmod(0o644)
            if name == package and (root / (name + ".sig")).exists():
                # A retry must reuse an existing signature: GPG timestamps make
                # independently generated signatures differ for identical bytes.
                shutil.copyfile(root / (name + ".sig"), stage / (name + ".sig"))
                run("gpg", "--batch", "--homedir", config["arch_gnupg_home"], "--verify",
                    stage / (name + ".sig"), stage / name)
            else:
                sign(config, stage / name)
            (stage / (name + ".sig")).chmod(0o644)
        immutable_copy(stage / package, root / package)
        immutable_copy(stage / (package + ".sig"), root / (package + ".sig"))
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        (stage / "manifest.json").chmod(0o644)
        # Keep package blobs in the stable directory, metadata in generations.
        (stage / package).unlink()
        (stage / (package + ".sig")).unlink()
        generations = root / "generations"
        generations.mkdir(exist_ok=True)
        generation = generations / manifest["tag"]
        if generation.exists():
            existing = json.loads((generation / "manifest.json").read_text())
            if existing != manifest:
                raise ValueError("retained Arch generation has different inputs")
            for name, digest in manifest["assets"].items():
                if name != package:
                    if sha256(generation / name) != digest:
                        raise ValueError("retained Arch generation is damaged")
                    run("gpg", "--batch", "--homedir", config["arch_gnupg_home"], "--verify",
                        generation / (name + ".sig"), generation / name)
        else:
            os.rename(stage, generation)
        for name in ("epithet.db", "epithet.files"):
            for suffix in ("", ".sig"):
                switch(root / (name + suffix), f"current/{name}.tar.gz{suffix}")
        switch(root / "current", f"generations/{manifest['tag']}")
    LOG.info("published Arch %s", manifest["tag"])


def current(config, target):
    root = Path(config["public_root"])
    if target == "freebsd":
        latest = root / config["freebsd_abi"] / "latest"
        tag = "v" + latest.resolve().name.split("_")[0] if latest.is_symlink() else None
        identity = latest / "release.json"
    else:
        latest = root / ("arch/x86_64" if target == "arch" else "macos") / "current"
        identity = latest / "manifest.json"
        tag = json.loads(identity.read_text())["tag"] if identity.exists() else None
    return tag, json.loads(identity.read_text()) if identity.exists() else None


def needed(config, target, release):
    tag, identity = current(config, target)
    if tag is None or version(tag) < version(release["tag"]):
        return True
    if tag == release["tag"] and (identity is None or any(identity.get(key) != value for key, value in release.items())):
        raise ValueError(f"{target} already has this version with different or unknown inputs")
    return False


def pending(config, tag, commit):
    """An idle poll need not reopen a completed release after recipe updates."""
    version(tag)
    result = False
    for target in ("freebsd", "arch", "macos"):
        published, identity = current(config, target)
        if published is None or version(published) < version(tag):
            result = True
        elif published == tag and (identity is None or identity.get("source_commit") != commit):
            raise ValueError(f"{target} has this version with different or unknown source identity")
    return result


def ruby_string(value):
    # Single-quoted Ruby strings do not interpolate #{...} in configured URLs.
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def formula(manifest, base_url, homepage):
    for value in (base_url, homepage):
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment or any(c.isspace() for c in value):
            raise ValueError("repository URL and homepage must be HTTPS URLs without query/fragment/whitespace")
    replacements = {"VERSION": manifest["tag"][1:], "HOMEPAGE": homepage}
    for arch in ("amd64", "arm64"):
        name = f"epithet_{manifest['tag'][1:]}_darwin_{arch}.tar.gz"
        replacements[arch.upper() + "_URL"] = base_url.rstrip("/") + "/macos/releases/" + manifest["tag"] + "/" + name
        replacements[arch.upper() + "_SHA256"] = manifest["assets"][name]
    result = (ROOT / "macos/epithet.rb.in").read_text()
    # One substitution pass prevents a configured value becoming a template.
    return re.sub(r"@@([A-Z0-9_]+)@@", lambda match: ruby_string(replacements[match[1]]), result)


def publish_macos(config, manifest, work):
    root = Path(config["public_root"]) / "macos"
    releases = root / "releases"
    releases.mkdir(parents=True, exist_ok=True)
    destination = releases / manifest["tag"]
    generated = formula(manifest, config["repository_url"], config["homepage"])
    (work / "epithet.rb").write_text(generated)
    if destination.exists():
        if json.loads((destination / "manifest.json").read_text()) != manifest:
            raise ValueError("retained macOS release has different inputs")
        for name, digest in manifest["assets"].items():
            if sha256(destination / name) != digest:
                raise ValueError("retained macOS release is damaged")
    else:
        with tempfile.TemporaryDirectory(prefix=".stage-", dir=root) as directory:
            stage = Path(directory)
            stage.chmod(0o755)
            for name in [*manifest["assets"], "manifest.json"]:
                shutil.copyfile(work / name, stage / name)
                (stage / name).chmod(0o644)
            os.rename(stage, destination)
    # Archives must already be served before clients can discover the formula.
    # If push fails, a retry reuses the identical archives and retries the tap.
    run(ROOT / "scripts/tap.sh", work.parent)
    switch(root / "current", f"releases/{manifest['tag']}")
    LOG.info("published macOS %s (packaging tests intentionally not run)", manifest["tag"])


def environment_config():
    return {"public_root": os.environ["PUBLIC_ROOT"], "freebsd_abi": os.environ.get("ABI", "FreeBSD:15:amd64"),
            "arch_gnupg_home": os.environ.get("ARCH_GNUPG_HOME", ""),
            "arch_key_fingerprint": os.environ.get("ARCH_KEY_FINGERPRINT", ""),
            "repository_url": os.environ.get("REPOSITORY_URL", ""), "homepage": os.environ.get("PROJECT_HOMEPAGE", "")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("arch", "freebsd", "macos", "needed", "pending", "status"))
    parser.add_argument("arguments", nargs="*")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = environment_config()
    if args.command == "pending":
        if not pending(config, *args.arguments):
            raise SystemExit(3)
        return
    if args.command == "status":
        print(json.dumps({target: current(config, target)[0] for target in ("freebsd", "arch", "macos")}))
        return
    if args.command == "needed":
        target, directory = args.arguments
        if not needed(config, target, read_release(directory)):
            raise SystemExit(3)
        return
    directory = Path(args.arguments[0])
    if args.command == "freebsd":
        if needed(config, "freebsd", read_release(directory)):
            raise ValueError("FreeBSD publisher did not promote this release")
        return
    manifest = verify(directory, args.command)
    if not needed(config, args.command, read_release(directory)):
        LOG.info("%s is already at this version or newer", args.command)
        return
    if args.command == "arch":
        publish_arch(config, manifest, directory / "arch")
    else:
        publish_macos(config, manifest, directory / "macos")


if __name__ == "__main__":
    main()
