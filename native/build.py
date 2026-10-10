"""Build native desktop archives on the operating system that will run them."""
import argparse
import hashlib
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parent.parent


def build_package(output_directory, smoke_test=False):
    architecture = {"AMD64": "x64", "x86_64": "x64", "aarch64": "arm64", "arm64": "arm64"}.get(platform.machine())
    if architecture is None:
        raise RuntimeError("Unsupported architecture: " + platform.machine())
    if sys.platform == "win32":
        system, extension, icon = "Windows", ".zip", "inknote.ico"
    elif sys.platform == "darwin":
        system, extension, icon = "macOS", ".zip", "inknote.icns"
    elif sys.platform.startswith("linux"):
        system, extension, icon = "Linux", ".tar.gz", None
    else:
        raise RuntimeError("Unsupported operating system: " + sys.platform)

    output_directory.mkdir(parents=True, exist_ok=True)
    build_directory = ROOT / "build-native"
    build_directory.mkdir(exist_ok=True)
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--onedir", "--windowed", "--name", "InkNote", "--noupx",
        "--paths", str(ROOT), "--distpath", str(output_directory),
        "--workpath", str(build_directory), "--specpath", str(build_directory),
    ]
    if icon:
        command.extend(["--icon", str(ROOT / "native" / "assets" / icon)])
    for source, destination in [
        ("licenses", "licenses"), ("THIRD_PARTY_NOTICES.txt", "."), ("QUICK_START.txt", "."),
    ]:
        command.extend(["--add-data", str(ROOT / "native" / source) + ":" + destination])
    if sys.platform == "darwin":
        command.extend(["--osx-bundle-identifier", "org.inknote.desktop"])
    command.append(str(ROOT / "native" / "app.py"))
    environment = os.environ.copy()
    if sys.platform == "win32":
        # Foreign ICU DLLs on PATH can shadow the Windows ICU library used by Qt.
        windows_directory = Path(environment["WINDIR"])
        environment["PATH"] = os.pathsep.join([str(windows_directory / "System32"), str(windows_directory)])
    subprocess.run(command, cwd=ROOT, env=environment, check=True)

    if sys.platform == "darwin":
        application_directory = output_directory / "InkNote.app"
        executable = application_directory / "Contents" / "MacOS" / "InkNote"
    else:
        application_directory = output_directory / "InkNote"
        executable = application_directory / ("InkNote.exe" if sys.platform == "win32" else "InkNote")
        # Keep the human-readable notices beside the executable as well as in the bundle.
        shutil.copytree(ROOT / "native" / "licenses", application_directory / "licenses", dirs_exist_ok=True)
        for filename in ("THIRD_PARTY_NOTICES.txt", "QUICK_START.txt"):
            shutil.copy2(ROOT / "native" / filename, application_directory / filename)

    if smoke_test:
        subprocess.run([str(executable), "--smoke-test"], cwd=ROOT, env=environment, check=True, timeout=45)

    archive = output_directory / f"InkNote-{system}-{architecture}{extension}"
    if sys.platform == "darwin":
        # ditto preserves the .app's framework symlinks and file permissions.
        subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
                        str(application_directory), str(archive)], check=True)
    elif sys.platform == "win32":
        shutil.make_archive(str(archive.with_suffix("")), "zip", output_directory, "InkNote")
    else:
        with tarfile.open(archive, "w:gz") as package:
            package.add(application_directory, arcname="InkNote")
    digest = hashlib.sha256()
    with archive.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    checksum = Path(str(archive) + ".sha256")
    # Linux sha256sum treats a Windows CRLF carriage return as part of the filename.
    checksum.write_text(digest.hexdigest() + "  " + archive.name + "\n", encoding="utf-8", newline="\n")
    print(archive)
    print(checksum)
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("desktop-dist"))
    parser.add_argument("--smoke-test", action="store_true", help="Launch the bundled app with isolated temporary drafts.")
    args = parser.parse_args()
    build_package(args.output_dir.resolve(), args.smoke_test)


if __name__ == "__main__":
    main()
