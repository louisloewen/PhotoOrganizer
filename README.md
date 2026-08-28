# Photo Organizer

A Python script that organizes photos, videos, and RAW files into a clean `Year/Month` folder structure with content-based duplicate detection.

## Features

- **Automatic date detection** — reads EXIF metadata, falls back to filename patterns
- **Content-based duplicate detection** — uses SHA-256 hashing to find duplicates regardless of filename
- **Separate media folders** — Photos, Videos, and RAW files each get their own organized tree
- **Multiple modes** — copy, move, reorganize in-place, or dry-run preview
- **Progress tracking** — real-time progress bar and detailed logging
- **Non-destructive** — duplicates are saved to a `_Duplicates/` folder, never deleted

## Output Structure

```
Destination/
├── Photos/                    ← .jpg, .png, .heic, .webp, etc.
│   ├── 2019/
│   │   ├── 01/
│   │   │   └── vacation.jpg
│   │   └── 06/
│   │       └── beach.png
│   └── Unknown/
├── Videos/                    ← .mp4, .mov, .avi, .mkv, etc.
│   ├── 2021/
│   │   └── 03/
│   │       └── DJI_0042.mp4
│   └── Unknown/
├── RAW/                       ← .cr2, .nef, .arw, .dng, etc.
│   ├── 2022/
│   │   └── 08/
│   │       └── IMG_5012.cr2
│   └── Unknown/
└── _Duplicates/
    ├── Photos/
    └── RAW/
```

## Setup

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/PhotoOrganizer.git
cd PhotoOrganizer

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install Pillow tqdm
```

## Usage

### Copy from Source to Destination

```bash
python3 photo_organizer.py --source /path/to/source --dest /path/to/destination
```

### Move (delete from source after transfer)

```bash
python3 photo_organizer.py --source /path/to/source --dest /path/to/destination --move
```

### Reorganize an Existing Folder

Restructure files already at a destination into the `Year/Month` layout:

```bash
python3 photo_organizer.py --reorganize --dest /path/to/destination
```

### Dry Run (preview without changes)

Add `--dry-run` to any command to see what would happen:

```bash
python3 photo_organizer.py --source /path/to/source --dest /path/to/destination --dry-run

# You can even preview without a destination
python3 photo_organizer.py --source /path/to/source --dry-run
```

### Custom Log File

```bash
python3 photo_organizer.py --source /path/to/source --dest /path/to/destination --log-file ~/Desktop/log.txt
```

## Duplicate Detection

| Media Type | Checked? | Method |
|------------|----------|--------|
| Photos     | ✅ Yes   | SHA-256 content hash |
| RAW        | ✅ Yes   | SHA-256 content hash |
| Videos     | ❌ No    | Skipped (large files, slow to hash) |

- Detects duplicates by **file content**, not filename
- Two identical photos with different names → caught
- Two different photos with the same name → both kept (auto-renamed)
- Duplicates are moved to `_Duplicates/`, never deleted

## Supported File Types

| Category | Extensions |
|----------|-----------|
| Photos   | `.jpg` `.jpeg` `.png` `.heic` `.tiff` `.tif` `.bmp` `.gif` `.webp` |
| Videos   | `.mp4` `.mov` `.avi` `.mkv` `.m4v` `.3gp` |
| RAW      | `.cr2` `.cr3` `.nef` `.arw` `.dng` `.raf` `.orf` `.rw2` |

## Use Scenarios

### Migrate an old HDD to an SSD

```bash
# Preview first
python3 photo_organizer.py --source '/Volumes/OldHDD' --dest /Volumes/SSD/Media --dry-run

# Run for real
python3 photo_organizer.py --source '/Volumes/OldHDD' --dest /Volumes/SSD/Media
```

### Clean up a messy folder structure

A third-party app created daily folders (`2019/May/23/`, `2019/May/24/`). Collapse them:

```bash
python3 photo_organizer.py --reorganize --dest /Volumes/SSD/Photos
```

### Merge multiple sources

Run the script once per source — duplicates across runs are caught automatically:

```bash
python3 photo_organizer.py --source /Volumes/USBStick/DCIM --dest ~/Pictures/Organized
python3 photo_organizer.py --source ~/OldBackup/Photos --dest ~/Pictures/Organized
python3 photo_organizer.py --source ~/Downloads --dest ~/Pictures/Organized
```

### Quick scan of a drive

See what's on a drive without committing to anything:

```bash
python3 photo_organizer.py --source '/Volumes/OldDrive' --dry-run
```

## Quick Reference

| Action | Command |
|--------|---------|
| Copy A → B | `--source A --dest B` |
| Move A → B | `--source A --dest B --move` |
| Reorganize B | `--reorganize --dest B` |
| Preview | Add `--dry-run` to any command |
| Quick scan | `--source A --dry-run` |
| Custom log | Add `--log-file /path/to/log.txt` |

## License

MIT
