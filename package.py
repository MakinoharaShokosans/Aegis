#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aegis Project Packaging Script
==============================
Packages the Aegis repository into a clean, reproducible ZIP archive
strictly adhering to .gitignore rules across all subprojects.

Features:
- Respects all .gitignore files (Root, AegisAgent, AegisRAG, AegisFrontend)
- Excludes .git, .env secrets, virtualenvs, build artifacts, node_modules, logs, and caches
- Preserves directory structures and essential .gitkeep files
- Supports custom output paths, compression levels, prefixing, and dry-run modes
- Zero external dependencies (pure Python standard library)

Usage:
    python package.py
    python package.py -o /tmp/Aegis_dist.zip
    python package.py --dry-run
    python package.py --no-prefix
"""

import argparse
import os
import subprocess
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple


def get_repo_root() -> Path:
    """Locate the root directory of the Aegis repository."""
    current = Path(__file__).resolve().parent
    # Check if .git or CLAUDE.MD / AegisAgent exists
    if (current / ".git").exists() or (current / "AegisAgent").exists():
        return current
    # Search upwards
    for parent in current.parents:
        if (parent / ".git").exists() or (parent / "AegisAgent").exists():
            return parent
    return current


def format_size(bytes_size: int) -> str:
    """Format bytes into human-readable strings (B, KB, MB, GB)."""
    if bytes_size < 1024:
        return f"{bytes_size} B"
    elif bytes_size < 1024 * 1024:
        return f"{bytes_size / 1024:.2f} KB"
    elif bytes_size < 1024 * 1024 * 1024:
        return f"{bytes_size / (1024 * 1024):.2f} MB"
    else:
        return f"{bytes_size / (1024 * 1024 * 1024):.2f} GB"


def collect_files_via_git(repo_root: Path, include_git: bool = False) -> List[Path]:
    """Collect non-ignored files using git ls-files."""
    cmd = ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"]
    try:
        result = subprocess.run(
            cmd,
            cwd=repo_root,
            capture_output=True,
            check=True,
        )
        raw_output = result.stdout
        # Split on null bytes to correctly handle UTF-8 / Chinese characters and spaces
        rel_paths = [p.decode("utf-8") for p in raw_output.split(b"\x00") if p]
    except (subprocess.CalledProcessError, FileNotFoundError) as err:
        print(f"[!] Warning: Git command failed ({err}). Falling back to filesystem walk.", file=sys.stderr)
        return fallback_collect_files(repo_root)

    valid_files: List[Path] = []
    for rel_p in rel_paths:
        full_path = repo_root / rel_p
        if full_path.is_file() or full_path.is_symlink():
            valid_files.append(Path(rel_p))

    if include_git:
        git_dir = repo_root / ".git"
        if git_dir.exists():
            for root, _, files in os.walk(git_dir):
                for f in files:
                    full_p = Path(root) / f
                    rel_p = full_p.relative_to(repo_root)
                    valid_files.append(rel_p)

    return sorted(valid_files)


def fallback_collect_files(repo_root: Path) -> List[Path]:
    """Fallback collector when git is not available."""
    default_ignores = {
        ".git", ".venv", "venv", "env", "node_modules", "dist", "dist-ssr", "build",
        "__pycache__", ".pytest_cache", ".hypothesis", ".mypy_cache", ".ruff_cache",
        "coverage", "htmlcov", "logs", ".vite", ".turbo", ".cache", ".fastembed",
        ".trafilatura", ".obsidian", ".idea", ".vscode"
    }
    collected: List[Path] = []
    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d not in default_ignores and not d.endswith(".egg-info")]
        for f in files:
            if f.endswith((".pyc", ".pyo", ".pyd", ".log", ".swp", ".swo", ".db", ".sqlite", ".zip", ".tar.gz")):
                continue
            if f.startswith(".env") and not f.endswith(".example"):
                continue
            full_path = Path(root) / f
            rel_p = full_path.relative_to(repo_root)
            collected.append(rel_p)
    return sorted(collected)


def package_project(
    repo_root: Path,
    output_zip: Path,
    prefix: Optional[str] = "Aegis",
    compress_level: int = 9,
    dry_run: bool = False,
    verbose: bool = False,
    include_git: bool = False,
    extra_excludes: Optional[List[str]] = None,
) -> Tuple[int, int, int]:
    """
    Package project files into a ZIP archive.
    Returns (file_count, uncompressed_size, compressed_size).
    """
    start_time = time.time()
    print(f"[*] Scanning files in repository: {repo_root}")
    files_to_pack = collect_files_via_git(repo_root, include_git=include_git)

    # Filter out output zip itself and extra excludes
    output_abs = output_zip.resolve()
    filtered_files: List[Path] = []
    
    for rel_path in files_to_pack:
        full_path = (repo_root / rel_path).resolve()
        # Prevent packaging the target zip file into itself
        if full_path == output_abs:
            continue
        
        # Check extra excludes
        if extra_excludes:
            skip = False
            rel_str = str(rel_path)
            for pattern in extra_excludes:
                if pattern in rel_str:
                    skip = True
                    break
            if skip:
                continue

        filtered_files.append(rel_path)

    total_uncompressed = 0
    for rel_path in filtered_files:
        full_path = repo_root / rel_path
        try:
            total_uncompressed += full_path.stat().st_size
        except OSError:
            pass

    print(f"[*] Found {len(filtered_files)} files to package ({format_size(total_uncompressed)} uncompressed).")

    if dry_run:
        print("\n[--- Dry Run: Files that would be packaged ---]")
        for i, rel_p in enumerate(filtered_files, 1):
            arcname = f"{prefix}/{rel_p}" if prefix else str(rel_p)
            print(f"  [{i:4d}] {arcname}")
        print(f"\n[✓] Dry run completed. Total: {len(filtered_files)} files.")
        return len(filtered_files), total_uncompressed, 0

    # Ensure output parent directory exists
    output_zip.parent.mkdir(parents=True, exist_ok=True)

    print(f"[*] Creating ZIP archive: {output_zip}")
    total_files = len(filtered_files)

    with zipfile.ZipFile(
        output_zip,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=compress_level,
    ) as zf:
        for idx, rel_path in enumerate(filtered_files, 1):
            full_path = repo_root / rel_path
            arcname = f"{prefix}/{rel_path}" if prefix else str(rel_path)

            if verbose:
                print(f"  [{idx}/{total_files}] Adding {rel_path} -> {arcname}")
            elif idx % 50 == 0 or idx == total_files:
                progress = (idx / total_files) * 100
                print(f"\r  Progress: {idx}/{total_files} ({progress:.1f}%)", end="", flush=True)

            zf.write(full_path, arcname=arcname)

    if not verbose:
        print()  # newline after progress bar

    compressed_size = output_zip.stat().st_size
    elapsed = time.time() - start_time
    ratio = (1 - (compressed_size / total_uncompressed)) * 100 if total_uncompressed > 0 else 0

    print("\n" + "=" * 60)
    print("           📦 Aegis Project Packaging Summary")
    print("=" * 60)
    print(f"  Target Archive     : {output_zip.resolve()}")
    print(f"  Included Files     : {total_files} files")
    print(f"  Uncompressed Size  : {format_size(total_uncompressed)}")
    print(f"  Compressed Size    : {format_size(compressed_size)}")
    print(f"  Compression Ratio  : {ratio:.1f}% space saved")
    print(f"  Elapsed Time       : {elapsed:.2f}s")
    print("=" * 60)
    print("[✓] Packaging completed successfully!\n")

    return total_files, total_uncompressed, compressed_size


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Package Aegis repository into a clean ZIP archive according to .gitignore.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Output ZIP file path (default: Aegis_YYYYMMDD_HHMMSS.zip in repo root)",
    )
    parser.add_argument(
        "--prefix",
        type=str,
        default="Aegis",
        help="Root folder prefix inside the archive (use '' or --no-prefix to disable)",
    )
    parser.add_argument(
        "--no-prefix",
        action="store_true",
        help="Do not wrap contents inside a top-level directory in the archive",
    )
    parser.add_argument(
        "-l", "--level",
        type=int,
        default=9,
        choices=range(1, 10),
        help="ZIP Deflate compression level (1-9)",
    )
    parser.add_argument(
        "-n", "--dry-run",
        action="store_true",
        help="Preview the list of files to be packaged without creating the archive",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print each file as it is added to the archive",
    )
    parser.add_argument(
        "--include-git",
        action="store_true",
        help="Include .git version control directory in the package",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Additional substring patterns to exclude from packaging",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    repo_root = get_repo_root()

    # Determine output zip file
    if args.output:
        output_zip = args.output
        if not str(output_zip).endswith(".zip"):
            output_zip = output_zip.with_suffix(".zip")
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_zip = repo_root / f"Aegis_{timestamp}.zip"

    prefix = None if args.no_prefix or not args.prefix else args.prefix

    package_project(
        repo_root=repo_root,
        output_zip=output_zip,
        prefix=prefix,
        compress_level=args.level,
        dry_run=args.dry_run,
        verbose=args.verbose,
        include_git=args.include_git,
        extra_excludes=args.exclude,
    )


if __name__ == "__main__":
    main()
