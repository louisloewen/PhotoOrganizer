#!/usr/bin/env python3
"""
Photo Organizer — Organize photos, videos, and RAW files into Year/Month folders
with content-based duplicate detection.

Usage:
    python photo_organizer.py --source /path/to/source --dest /path/to/destination
    python photo_organizer.py --reorganize --dest /path/to/destination
    python photo_organizer.py --source /path/to/source --dest /path/to/destination --dry-run

Dependencies:
    pip install Pillow tqdm
"""

import argparse
import hashlib
import logging
import os
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

try:
    from PIL import Image, ExifTags
except ImportError:
    print("Error: Pillow is required. Install it with: pip install Pillow")
    sys.exit(1)

try:
    from tqdm import tqdm
except ImportError:
    print("Error: tqdm is required. Install it with: pip install tqdm")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PHOTO_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".heic", ".tiff", ".tif",
    ".bmp", ".gif", ".webp",
}

VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv", ".m4v", ".3gp",
}

RAW_EXTENSIONS = {
    ".cr2", ".cr3", ".nef", ".arw", ".dng", ".raf", ".orf", ".rw2",
}

ALL_EXTENSIONS = PHOTO_EXTENSIONS | VIDEO_EXTENSIONS | RAW_EXTENSIONS

UNKNOWN_FOLDER = "Unknown"
DUPLICATES_FOLDER = "_Duplicates"

# Files to always ignore (system/hidden files)
IGNORED_FILES = {
    ".ds_store", "thumbs.db", "desktop.ini", ".localized",
    "photo_organizer.log",
}

# EXIF tag IDs for date fields
EXIF_DATE_TAGS = {
    36867: "DateTimeOriginal",
    36868: "DateTimeDigitized",
    306:   "DateTime",
}

# Priority order for date extraction
EXIF_DATE_PRIORITY = [36867, 36868, 306]

EXIF_DATE_FORMAT = "%Y:%m:%d %H:%M:%S"


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def setup_logging(log_file: str | None, dest: str) -> logging.Logger:
    """Configure logging to both console and file."""
    logger = logging.getLogger("photo_organizer")
    logger.setLevel(logging.DEBUG)

    # Console handler — INFO and above
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(console)

    # File handler — DEBUG and above (detailed log)
    # Skip file logging when dest is a placeholder (dry run without --dest)
    if dest is not None and not dest.startswith("<"):
        if log_file is None:
            log_file = os.path.join(dest, "photo_organizer.log")
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s"))
        logger.addHandler(fh)

    return logger


# ---------------------------------------------------------------------------
# Date extraction
# ---------------------------------------------------------------------------

def get_date_from_exif(filepath: str) -> datetime | None:
    """
    Attempt to extract the date taken from EXIF metadata.
    Tries DateTimeOriginal, DateTimeDigitized, then DateTime in that order.
    Returns None if no EXIF date is found.
    """
    try:
        with Image.open(filepath) as img:
            exif_data = img.getexif()
            if not exif_data:
                return None

            for tag_id in EXIF_DATE_PRIORITY:
                value = exif_data.get(tag_id)
                if value:
                    try:
                        return datetime.strptime(str(value).strip(), EXIF_DATE_FORMAT)
                    except (ValueError, TypeError):
                        continue
    except Exception:
        # Not an image Pillow can open (e.g. video, unsupported RAW)
        pass

    return None


def get_date_from_filename(filepath: str) -> datetime | None:
    """
    Try to extract a date from common filename patterns.
    Handles patterns like:
        IMG_20190523_143022.jpg
        20190523_143022.jpg
        2019-05-23 14.30.22.jpg
        VID_20190523_143022.mp4
    """
    import re

    basename = os.path.splitext(os.path.basename(filepath))[0]

    patterns = [
        # IMG_20190523_143022 or VID_20190523_143022 or 20190523_143022
        (r"(\d{4})(\d{2})(\d{2})[_\-](\d{2})(\d{2})(\d{2})",
         lambda m: datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                            int(m.group(4)), int(m.group(5)), int(m.group(6)))),
        # 2019-05-23 or 2019_05_23
        (r"(\d{4})[_\-](\d{2})[_\-](\d{2})",
         lambda m: datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))),
        # 20190523 (8 consecutive digits that look like a date)
        (r"(?<!\d)(\d{4})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)",
         lambda m: datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))),
    ]

    for pattern, parser in patterns:
        match = re.search(pattern, basename)
        if match:
            try:
                dt = parser(match)
                # Sanity check: year between 1900 and 2100
                if 1900 <= dt.year <= 2100:
                    return dt
            except (ValueError, OverflowError):
                continue

    return None


def get_file_date(filepath: str) -> datetime | None:
    """
    Get the best available date for a file.
    Priority: EXIF → filename pattern → None (Unknown folder).
    """
    # 1. Try EXIF
    date = get_date_from_exif(filepath)
    if date:
        return date

    # 2. Try filename patterns
    date = get_date_from_filename(filepath)
    if date:
        return date

    # 3. No date found
    return None


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

def hash_file(filepath: str) -> str:
    """Compute SHA-256 hash of a file's content, reading in 64KB chunks."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            sha256.update(chunk)
    return sha256.hexdigest()


# ---------------------------------------------------------------------------
# Destination indexing
# ---------------------------------------------------------------------------

def index_destination(dest: str, logger: logging.Logger) -> dict[str, str]:
    """
    Walk the destination directory and build a hash → filepath mapping
    of all existing supported files. This lets us detect duplicates
    against what's already organized.
    """
    hash_map: dict[str, str] = {}
    duplicates_path = os.path.join(dest, DUPLICATES_FOLDER)

    # Collect files first to show progress
    files_to_index = []
    for root, _dirs, files in os.walk(dest):
        # Skip the _Duplicates folder itself
        if os.path.abspath(root).startswith(os.path.abspath(duplicates_path)):
            continue
        for fname in files:
            fpath = os.path.join(root, fname)
            ext = os.path.splitext(fname)[1].lower()
            # Only index photos and RAW files (videos skip duplicate detection)
            if ext in PHOTO_EXTENSIONS or ext in RAW_EXTENSIONS:
                files_to_index.append(fpath)

    if not files_to_index:
        logger.info("No existing files found at destination to index.")
        return hash_map

    logger.info(f"Indexing {len(files_to_index)} existing files at destination...")
    for fpath in tqdm(files_to_index, desc="Indexing destination", unit="file"):
        try:
            h = hash_file(fpath)
            hash_map[h] = fpath
        except (OSError, PermissionError) as e:
            logger.warning(f"Could not hash {fpath}: {e}")

    logger.info(f"Indexed {len(hash_map)} unique files at destination.")
    return hash_map


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def get_dest_folder(dest: str, file_date: datetime | None, category: str = "") -> str:
    """Return the target folder path: dest/Category/YYYY/MM or dest/Category/Unknown."""
    base = os.path.join(dest, category) if category else dest
    # "Other" files go straight into Other/ with no date subfolders
    if category == "Other":
        return base
    if file_date is None:
        return os.path.join(base, UNKNOWN_FOLDER)
    year = str(file_date.year)
    month = f"{file_date.month:02d}"
    return os.path.join(base, year, month)


def get_unique_filepath(folder: str, filename: str) -> str:
    """
    If a file with the same name already exists in the folder,
    append a counter until we find a unique name.
    photo.jpg → photo_1.jpg → photo_2.jpg → ...
    """
    target = os.path.join(folder, filename)
    if not os.path.exists(target):
        return target

    name, ext = os.path.splitext(filename)
    counter = 1
    while True:
        new_name = f"{name}_{counter}{ext}"
        target = os.path.join(folder, new_name)
        if not os.path.exists(target):
            return target
        counter += 1


def get_media_category(filepath: str) -> str:
    """Determine the media category based on file extension."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext in PHOTO_EXTENSIONS:
        return "Photos"
    elif ext in VIDEO_EXTENSIONS:
        return "Videos"
    elif ext in RAW_EXTENSIONS:
        return "RAW"
    return "Other"


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def collect_files(source: str) -> list[str]:
    """Recursively collect all files from the source directory (excluding system/hidden files)."""
    files = []
    for root, _dirs, filenames in os.walk(source):
        for fname in filenames:
            # Skip hidden files and known system files
            if fname.startswith(".") or fname.lower() in IGNORED_FILES:
                continue
            files.append(os.path.join(root, fname))
    return files


def process_file(
    filepath: str,
    dest: str,
    hash_map: dict[str, str],
    stats: dict[str, int],
    logger: logging.Logger,
    dry_run: bool = False,
    move: bool = False,
) -> None:
    """
    Process a single file: determine category (Photos/Videos/RAW),
    extract date, check for duplicates (photos & RAW only),
    copy/move to the correct Category/Year/Month folder.
    """
    filename = os.path.basename(filepath)
    category = get_media_category(filepath)

    # 1. Duplicate detection (only for photos & RAW)
    file_hash = None
    if category in ("Photos", "RAW"):
        try:
            file_hash = hash_file(filepath)
        except (OSError, PermissionError) as e:
            logger.error(f"SKIP (cannot read): {filepath} — {e}")
            stats["errors"] += 1
            return

        if file_hash in hash_map:
            existing = hash_map[file_hash]
            logger.debug(f"DUPLICATE: {filepath} == {existing}")

            file_date = get_file_date(filepath)
            dup_folder = get_dest_folder(
                os.path.join(dest, DUPLICATES_FOLDER), file_date, category
            )

            if not dry_run:
                os.makedirs(dup_folder, exist_ok=True)
                dup_target = get_unique_filepath(dup_folder, filename)
                shutil.copy2(filepath, dup_target)
                logger.debug(f"  → Saved duplicate to {dup_target}")
            else:
                logger.info(f"[DRY RUN] Would save duplicate: {filepath} → {dup_folder}/{filename}")

            stats["duplicates"] += 1
            return

    # 2. Extract date (skip for Other files — they just go in a flat folder)
    file_date = None
    if category != "Other":
        file_date = get_file_date(filepath)
        if file_date is None:
            stats["no_date"] += 1

    # 3. Determine destination folder (routed by category)
    target_folder = get_dest_folder(dest, file_date, category)

    # 4. Handle filename conflicts
    target_path = get_unique_filepath(target_folder, filename)

    # 5. Copy or move
    action = "MOVE" if move else "COPY"
    if not dry_run:
        os.makedirs(target_folder, exist_ok=True)
        if move:
            shutil.move(filepath, target_path)
        else:
            shutil.copy2(filepath, target_path)
        logger.debug(f"{action}: {filepath} → {target_path}")
    else:
        logger.info(f"[DRY RUN] Would {action.lower()}: {filepath} → {target_path}")

    # 6. Register in hash map (only for photos & RAW)
    if file_hash is not None:
        hash_map[file_hash] = target_path
    stats["processed"] += 1


def organize(
    source: str,
    dest: str,
    dry_run: bool = False,
    move: bool = False,
    logger: logging.Logger | None = None,
) -> dict[str, int]:
    """
    Main organization routine.
    Copies/moves files from source into dest/Year/Month structure.
    """
    if logger is None:
        logger = logging.getLogger("photo_organizer")

    stats: dict[str, int] = defaultdict(int)

    # Validate paths
    if not os.path.isdir(source):
        logger.error(f"Source directory does not exist: {source}")
        sys.exit(1)

    # Make sure source and dest are not the same
    if os.path.abspath(source) == os.path.abspath(dest):
        logger.error("Source and destination cannot be the same directory. Use --reorganize instead.")
        sys.exit(1)

    if not dry_run:
        os.makedirs(dest, exist_ok=True)

    # Index destination
    hash_map = index_destination(dest, logger)

    # Collect source files
    logger.info(f"Scanning source: {source}")
    files = collect_files(source)
    logger.info(f"Found {len(files)} supported files in source.")

    if not files:
        logger.info("Nothing to do.")
        return dict(stats)

    # Process each file
    for filepath in tqdm(files, desc="Organizing files", unit="file"):
        process_file(filepath, dest, hash_map, stats, logger, dry_run, move)

    return dict(stats)


def reorganize(
    dest: str,
    dry_run: bool = False,
    logger: logging.Logger | None = None,
) -> dict[str, int]:
    """
    Reorganize existing files at dest into Year/Month structure.
    This collapses day-based folders and any other structure into Year/Month.
    Moves files within the destination — originals are relocated, not copied.
    """
    if logger is None:
        logger = logging.getLogger("photo_organizer")

    stats: dict[str, int] = defaultdict(int)

    if not os.path.isdir(dest):
        logger.error(f"Destination directory does not exist: {dest}")
        sys.exit(1)

    duplicates_path = os.path.abspath(os.path.join(dest, DUPLICATES_FOLDER))
    unknown_path = os.path.abspath(os.path.join(dest, UNKNOWN_FOLDER))

    # Collect all files currently at dest (excluding _Duplicates)
    files = []
    for root, _dirs, filenames in os.walk(dest):
        abs_root = os.path.abspath(root)
        if abs_root.startswith(duplicates_path):
            continue
        for fname in filenames:
            # Skip hidden files and known system files
            if fname.startswith(".") or fname.lower() in IGNORED_FILES:
                continue
            files.append(os.path.join(root, fname))

    logger.info(f"Found {len(files)} files to reorganize at destination.")

    if not files:
        logger.info("Nothing to reorganize.")
        return dict(stats)

    # Build hash map for duplicate detection during reorganization
    hash_map: dict[str, str] = {}

    for filepath in tqdm(files, desc="Reorganizing", unit="file"):
        filename = os.path.basename(filepath)
        category = get_media_category(filepath)

        # Duplicate detection (only for photos & RAW)
        file_hash = None
        if category in ("Photos", "RAW"):
            try:
                file_hash = hash_file(filepath)
            except (OSError, PermissionError) as e:
                logger.error(f"SKIP (cannot read): {filepath} — {e}")
                stats["errors"] += 1
                continue

            # Check for duplicate within destination itself
            if file_hash in hash_map:
                existing = hash_map[file_hash]
                logger.debug(f"DUPLICATE (internal): {filepath} == {existing}")

                file_date = get_file_date(filepath)
                dup_folder = get_dest_folder(
                    os.path.join(dest, DUPLICATES_FOLDER), file_date, category
                )

                if not dry_run:
                    os.makedirs(dup_folder, exist_ok=True)
                    dup_target = get_unique_filepath(dup_folder, filename)
                    shutil.move(filepath, dup_target)
                    logger.debug(f"  → Moved internal duplicate to {dup_target}")
                else:
                    logger.info(f"[DRY RUN] Would move internal duplicate: {filepath} → {dup_folder}/{filename}")

                stats["duplicates"] += 1
                continue

        # Determine correct location
        file_date = None
        if category != "Other":
            file_date = get_file_date(filepath)
            if file_date is None:
                stats["no_date"] += 1

        target_folder = get_dest_folder(dest, file_date, category)
        target_path = get_unique_filepath(target_folder, filename)

        # Skip if already in the correct location
        if os.path.abspath(filepath) == os.path.abspath(target_path):
            if file_hash is not None:
                hash_map[file_hash] = filepath
            stats["already_organized"] += 1
            continue

        # Move to correct location
        if not dry_run:
            os.makedirs(target_folder, exist_ok=True)
            shutil.move(filepath, target_path)
            logger.debug(f"REORGANIZE: {filepath} → {target_path}")
        else:
            logger.info(f"[DRY RUN] Would move: {filepath} → {target_path}")

        if file_hash is not None:
            hash_map[file_hash] = target_path
        stats["processed"] += 1

    # Clean up empty directories
    if not dry_run:
        cleanup_empty_dirs(dest, logger)

    return dict(stats)


def cleanup_empty_dirs(directory: str, logger: logging.Logger) -> None:
    """Remove empty directories left behind after moving files."""
    for root, dirs, files in os.walk(directory, topdown=False):
        for d in dirs:
            dirpath = os.path.join(root, d)
            try:
                if not os.listdir(dirpath):
                    os.rmdir(dirpath)
                    logger.debug(f"Removed empty directory: {dirpath}")
            except OSError:
                pass


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def print_summary(stats: dict[str, int], mode: str) -> None:
    """Print a formatted summary of the operation."""
    print("\n" + "=" * 50)
    print("  SUMMARY")
    print("=" * 50)
    print(f"  Mode:              {mode}")
    print(f"  Files organized:   {stats.get('processed', 0)}")
    print(f"  Duplicates found:  {stats.get('duplicates', 0)}")
    print(f"  No date (Unknown): {stats.get('no_date', 0)}")
    if stats.get("already_organized", 0) > 0:
        print(f"  Already organized: {stats.get('already_organized', 0)}")
    if stats.get("errors", 0) > 0:
        print(f"  Errors:            {stats.get('errors', 0)}")
    print("=" * 50 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Organize photos, videos, and RAW files into Year/Month folders "
                    "with content-based duplicate detection.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Copy photos from source to destination
  python photo_organizer.py --source /Volumes/HDD/Photos --dest /Volumes/SSD/Photos

  # Move instead of copy
  python photo_organizer.py --source /Volumes/HDD/Photos --dest /Volumes/SSD/Photos --move

  # Reorganize existing destination into Year/Month
  python photo_organizer.py --reorganize --dest /Volumes/SSD/Photos

  # Preview without making changes
  python photo_organizer.py --source /Volumes/HDD/Photos --dest /Volumes/SSD/Photos --dry-run
        """,
    )

    parser.add_argument(
        "--source",
        type=str,
        help="Source directory containing photos to organize.",
    )
    parser.add_argument(
        "--dest",
        type=str,
        help="Destination directory for organized photos (optional with --dry-run).",
    )
    parser.add_argument(
        "--move",
        action="store_true",
        default=False,
        help="Move files instead of copying (deletes from source after transfer).",
    )
    parser.add_argument(
        "--reorganize",
        action="store_true",
        default=False,
        help="Reorganize existing files at --dest into Year/Month structure.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview all actions without making any changes.",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Path to save the detailed log file (defaults to photo_organizer.log in dest).",
    )

    args = parser.parse_args()

    # Validation
    if not args.reorganize and not args.source:
        parser.error("--source is required unless using --reorganize.")

    if not args.dest and not args.dry_run:
        parser.error("--dest is required unless using --dry-run.")

    if args.reorganize and not args.dest:
        parser.error("--dest is required when using --reorganize.")

    if args.reorganize and args.source:
        parser.error("--source cannot be used with --reorganize. "
                      "Reorganize works on the --dest directory only.")

    if args.reorganize and args.move:
        parser.error("--move cannot be used with --reorganize "
                      "(reorganize always moves files within the destination).")

    # Setup
    # Handle optional --dest during dry runs
    if args.dest:
        dest = os.path.abspath(args.dest)
        os.makedirs(dest, exist_ok=True)
    else:
        dest = "<destination>"  # Placeholder for dry-run display

    logger = setup_logging(args.log_file, dest)

    if args.dry_run:
        logger.info("=" * 50)
        logger.info("  DRY RUN — no files will be modified")
        logger.info("=" * 50)

    # Run
    if args.reorganize:
        logger.info(f"Reorganizing: {dest}")
        stats = reorganize(dest, dry_run=args.dry_run, logger=logger)
        print_summary(stats, "Reorganize" + (" (dry run)" if args.dry_run else ""))
    else:
        source = os.path.abspath(args.source)
        action = "Moving" if args.move else "Copying"
        logger.info(f"{action} from: {source}")
        logger.info(f"          to: {dest}")
        stats = organize(source, dest, dry_run=args.dry_run, move=args.move, logger=logger)
        mode = ("Move" if args.move else "Copy") + (" (dry run)" if args.dry_run else "")
        print_summary(stats, mode)

    logger.info("Done!")


if __name__ == "__main__":
    main()
