from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterable


def prepare_output_root(
    output_parent_dir: Path,
    *,
    legacy_dir_globs: Iterable[str] = (),
    legacy_marker_dirs: Iterable[str] = (),
    current_dir_patterns: Iterable[str] = (),
) -> Path:
    output_parent_dir.mkdir(parents=True, exist_ok=True)
    extracted_root = output_parent_dir / "extracted"
    extracted_root.mkdir(parents=True, exist_ok=True)

    for glob_pattern in legacy_dir_globs:
        for legacy in output_parent_dir.glob(glob_pattern):
            if legacy == extracted_root or not legacy.is_dir():
                continue
            shutil.rmtree(legacy, ignore_errors=True)

    marker_dirs = tuple(legacy_marker_dirs)
    if marker_dirs:
        for legacy in output_parent_dir.glob("Extracted_*"):
            if legacy == extracted_root or not legacy.is_dir():
                continue
            if any((legacy / marker_dir).exists() for marker_dir in marker_dirs):
                shutil.rmtree(legacy, ignore_errors=True)

    for dir_pattern in current_dir_patterns:
        for existing in extracted_root.glob(dir_pattern):
            if existing.is_dir():
                shutil.rmtree(existing, ignore_errors=True)

    return extracted_root


def prepare_shared_sample_dir(output_dir: Path, run_stamp: str) -> Path:
    sample_dir = output_dir / f"_test_samples_{run_stamp}"
    sample_dir.mkdir(parents=True, exist_ok=True)

    legacy_sample_dir = output_dir / "_test_samples"
    if legacy_sample_dir.is_dir():
        for item in legacy_sample_dir.iterdir():
            target = sample_dir / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            else:
                shutil.copy2(item, target)
        shutil.rmtree(legacy_sample_dir, ignore_errors=True)

    for existing in sorted(output_dir.glob("_test_samples_*")):
        if existing == sample_dir or not existing.is_dir():
            continue
        for item in existing.iterdir():
            target = sample_dir / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            else:
                shutil.copy2(item, target)
        shutil.rmtree(existing, ignore_errors=True)

    return sample_dir
