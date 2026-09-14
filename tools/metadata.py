"""Small data helpers for the shell release pipeline: identity, hashes, archives.

The source repository and installed recipes are trusted operator inputs. A
release freezes both identities, then every result records its exact bytes.
"""
import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parent.parent


def version(tag):
    if not isinstance(tag, str) or not re.fullmatch(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", tag):
        raise ValueError(f"not a stable version: {tag!r}")
    return tuple(map(int, tag[1:].split(".")))


def sha256(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    temporary = Path(str(path) + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    os.replace(temporary, path)


def read_release(directory):
    data = json.loads((Path(directory) / "release.json").read_text())
    version(data["tag"])
    for key, length in (("source_commit", 40), ("recipe_digest", 64)):
        if not re.fullmatch(r"[a-f0-9]{%d}" % length, str(data[key])):
            raise ValueError(f"invalid {key}")
    if type(data["source_epoch"]) is not int or data["source_epoch"] < 0:
        raise ValueError("invalid source epoch")
    return data


def recipe_digest():
    digest = hashlib.sha256()
    for directory in ("bin", "scripts", "tools", "arch", "freebsd/port", "freebsd/ops", "macos", "tests"):
        for path in sorted((ROOT / directory).rglob("*")):
            if "__pycache__" in path.parts or path.suffix == ".pyc" or path.suffix == ".md":
                continue
            if path.is_symlink():
                raise ValueError(f"recipe is a symlink: {path}")
            if path.is_file():
                record = [path.relative_to(ROOT).as_posix(), bool(path.stat().st_mode & 0o111), sha256(path)]
                digest.update(json.dumps(record).encode() + b"\n")
    return digest.hexdigest()


def prepare(tag, commit):
    version(tag)
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("release requires a full source commit")
    git = ["git", "--git-dir=" + os.environ["SOURCE_CACHE"]]
    resolved = subprocess.check_output(git + ["rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}"], text=True).strip()
    if resolved != commit:
        raise ValueError("tag does not resolve to the requested source commit")
    epoch = int(subprocess.check_output(git + ["show", "-s", "--format=%ct", commit], text=True))
    data = {"tag": tag, "source_commit": commit, "source_epoch": epoch, "recipe_digest": recipe_digest()}
    directory = Path(os.environ["WORK_ROOT"]) / tag
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "release.json"
    if path.exists():
        if read_release(directory) != data:
            raise ValueError("release inputs changed; use a new version or explicitly remove an unpublished workspace")
    else:
        write_json(path, data)


def archive(source, destination, epoch):
    """Deterministic tar.gz used for vendored sources and macOS distributions."""
    source = Path(source)
    with open(destination, "wb") as output, gzip.GzipFile(filename="", fileobj=output, mode="wb", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as tar:
            for path in sorted(source.rglob("*")):
                if not path.is_file() and not path.is_dir():
                    raise ValueError(f"archive contains unsupported entry: {path}")
                if path.is_symlink():
                    raise ValueError(f"archive contains symlink: {path}")
                info = tar.gettarinfo(str(path), arcname=path.relative_to(source).as_posix())
                info.uid = info.gid = 0
                info.uname = info.gname = "root"
                info.mtime = int(epoch)
                info.mode = 0o755 if path.is_dir() or path.stat().st_mode & 0o111 else 0o644
                if info.isfile():
                    with path.open("rb") as stream:
                        tar.addfile(info, stream)
                else:
                    tar.addfile(info)


def source_hash(directory):
    path = Path(directory)
    expected = (path / "source.sha256").read_text().strip()
    if not re.fullmatch(r"[a-f0-9]{64}", expected) or sha256(path / "source.tar.gz") != expected:
        raise ValueError("source archive changed or is incomplete")
    return expected


def asset_names(target, tag):
    if target == "arch":
        return [f"epithet-{tag[1:]}-1-x86_64.pkg.tar.zst", "epithet.db.tar.gz", "epithet.files.tar.gz"]
    if target == "macos":
        return [f"epithet_{tag[1:]}_darwin_{arch}.tar.gz" for arch in ("amd64", "arm64")]
    raise ValueError("unknown artifact target")


def receipt(directory, target):
    data = read_release(directory)
    data.update({"target": target, "source_sha256": source_hash(directory),
                 "tests": "pacman" if target == "arch" else "not-run"})
    output = Path(directory) / target
    data["assets"] = {name: sha256(output / name) for name in asset_names(target, data["tag"])}
    write_json(output / "manifest.json", data)


def verify(directory, target):
    data = read_release(directory)
    output = Path(directory) / target
    manifest = json.loads((output / "manifest.json").read_text())
    if (any(manifest.get(key) != value for key, value in data.items())
            or manifest.get("target") != target
            or manifest.get("source_sha256") != source_hash(directory)
            or manifest.get("tests") != ("pacman" if target == "arch" else "not-run")
            or set(manifest.get("assets", {})) != set(asset_names(target, data["tag"]))):
        raise ValueError("artifacts do not match this release")
    for name, digest in manifest["assets"].items():
        if not (output / name).is_file() or (output / name).is_symlink() or sha256(output / name) != digest:
            raise ValueError(f"artifact changed or is incomplete: {name}")
    return manifest


def unpack_result(archive_path, directory):
    """The SSH result contains only fixed-name, regular files; never extract links."""
    directory = Path(directory)
    expected = set(asset_names("arch", read_release(directory)["tag"])) | {"manifest.json"}
    with tarfile.open(archive_path) as tar:
        members = tar.getmembers()
        if len(members) != len(expected) or {m.name for m in members} != expected or any(not m.isfile() for m in members):
            raise ValueError("unexpected Arch result archive")
        output = directory / "arch"
        output.mkdir(exist_ok=True)
        for member in members:
            (output / member.name).write_bytes(tar.extractfile(member).read())
    verify(directory, "arch")


def check_tap(path, tag):
    path = Path(path)
    if not path.exists():
        return
    match = re.search(r"^\s*version\s+['\"]([0-9]+\.[0-9]+\.[0-9]+)['\"]\s*$", path.read_text(), re.M)
    if match is None:
        raise ValueError("cannot determine existing tap version; inspect the formula before migration")
    if version("v" + match[1]) > version(tag):
        raise ValueError("refusing to downgrade the Homebrew tap")


def main():
    command, *args = sys.argv[1:]
    if command == "latest":
        tags = []
        for line in sys.stdin:
            try:
                version(line.strip())
                tags.append(line.strip())
            except ValueError:
                continue
        print(max(tags, key=version) if tags else "")
    elif command == "prepare":
        prepare(*args)
    elif command == "environment":
        data = read_release(args[0])
        values = {"TAG": data["tag"], "VERSION": data["tag"][1:], "SOURCE_COMMIT": data["source_commit"],
                  "SOURCE_EPOCH": data["source_epoch"], "BUILD_DATE": datetime.datetime.fromtimestamp(
                      data["source_epoch"], datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        print("\n".join(f"{key}={shlex.quote(str(value))}" for key, value in values.items()))
    elif command == "archive":
        archive(*args)
    elif command == "seal-source":
        directory, source = map(Path, args)
        (directory / "source.sha256").write_text(sha256(source) + "\n")
        os.replace(source, directory / "source.tar.gz")
    elif command == "verify-source":
        source_hash(args[0])
    elif command == "receipt":
        receipt(*args)
    elif command == "verify":
        verify(*args)
    elif command == "unpack-result":
        unpack_result(*args)
    elif command == "check-tap":
        check_tap(*args)
    else:
        raise ValueError("unknown metadata operation")


if __name__ == "__main__":
    main()
