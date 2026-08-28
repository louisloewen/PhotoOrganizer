# Photo Organizer

A Python script that organizes photos, videos, RAW files, and other documents into a clean folder structure with content-based duplicate detection.

## Features

- **Automatic date detection** — reads EXIF metadata, falls back to filename patterns
- **Content-based duplicate detection** — uses SHA-256 hashing to find duplicates regardless of filename (photos & RAW only)
- **Separate media folders** — Photos, Videos, RAW, and Other files each get their own organized tree
- **Multiple modes** — copy, move, reorganize in-place, or dry-run preview
- **Progress tracking** — real-time progress bar and detailed logging
- **Non-destructive** — duplicates are saved to a `_Duplicates/` folder, never deleted
- **Cross-platform** — works on macOS, Windows, and Linux

## Output Structure

```
Destination/
├── Photos/                    ← .jpg, .png, .heic, .webp, etc.
│   ├── 2019/
│   │   ├── 01/
│   │   │   └── vacation.jpg
│   │   └── 06/
│   │       └── beach.png
│   └── Unknown/               ← photos with no date info
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
├── Other/                     ← .pdf, .docx, .exe, everything else (flat, no date sorting)
│   ├── resume.docx
│   └── notes.txt
└── _Duplicates/               ← duplicate photos & RAW
    ├── Photos/
    └── RAW/
```

---

## Setup

### macOS / Linux

```bash
# Clone the repo
git clone https://github.com/louisloewen/PhotoOrganizer.git
cd PhotoOrganizer

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install Pillow tqdm
```

### Windows

```powershell
# Clone the repo
git clone https://github.com/louisloewen/PhotoOrganizer.git
cd PhotoOrganizer

# Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install Pillow tqdm
```

> **Note:** On Windows, use `python` instead of `python3` in all commands below. If `python` isn't recognized, try `py` instead.

---

## Usage

### Copy from Source to Destination

Copies files from one place to another. Originals are untouched.

**macOS / Linux:**
```bash
python3 photo_organizer.py --source /path/to/source --dest /path/to/destination
```

**Windows:**
```powershell
python photo_organizer.py --source "D:\OldPhotos" --dest "E:\OrganizedPhotos"
```

---

### Move (delete from source after transfer)

```bash
# macOS / Linux
python3 photo_organizer.py --source /path/to/source --dest /path/to/destination --move

# Windows
python photo_organizer.py --source "D:\OldPhotos" --dest "E:\OrganizedPhotos" --move
```

> **Warning:** This removes files from the source after they're transferred. Only use when you're sure.

---

### Reorganize an Existing Folder

Restructure files already at a location into the organized layout:

```bash
# macOS / Linux
python3 photo_organizer.py --reorganize --dest /path/to/destination

# Windows
python photo_organizer.py --reorganize --dest "E:\OrganizedPhotos"
```

---

### Dry Run (preview without changes)

Add `--dry-run` to any command to see what would happen without touching files:

```bash
# macOS / Linux
python3 photo_organizer.py --source /path/to/source --dest /path/to/destination --dry-run

# Preview without even specifying a destination
python3 photo_organizer.py --source /path/to/source --dry-run

# Windows
python photo_organizer.py --source "D:\OldPhotos" --dest "E:\OrganizedPhotos" --dry-run
python photo_organizer.py --source "D:\OldPhotos" --dry-run
```

---

### Custom Log File

```bash
# macOS / Linux
python3 photo_organizer.py --source /path/to/source --dest /path/to/destination --log-file ~/Desktop/log.txt

# Windows
python photo_organizer.py --source "D:\OldPhotos" --dest "E:\OrganizedPhotos" --log-file "C:\Users\You\Desktop\log.txt"
```

---

## How It Works

### Date Detection (Priority Order)

| Priority | Method | Example |
|----------|--------|---------|
| 1st | EXIF metadata (camera date) | Camera wrote `2019:05:23 14:30:22` inside the file |
| 2nd | Filename pattern | `IMG_20190523_143022.jpg` → May 23, 2019 |
| 3rd | No date found | File goes to `Unknown/` subfolder |

### Duplicate Detection

| Media Type | Checked? | Method |
|------------|----------|--------|
| Photos     | ✅ Yes   | SHA-256 content hash |
| RAW        | ✅ Yes   | SHA-256 content hash |
| Videos     | ❌ No    | Skipped (large files, slow to hash) |
| Other      | ❌ No    | Skipped |

- Detects duplicates by **file content**, not filename
- Two identical photos with different names → caught as duplicate
- Two different photos with the same name → both kept (auto-renamed)
- Duplicates are moved to `_Duplicates/`, never deleted

### File Categories

| Category | Extensions | Organization |
|----------|-----------|-------------|
| Photos   | `.jpg` `.jpeg` `.png` `.heic` `.tiff` `.tif` `.bmp` `.gif` `.webp` | `Year/Month` folders |
| Videos   | `.mp4` `.mov` `.avi` `.mkv` `.m4v` `.3gp` | `Year/Month` folders |
| RAW      | `.cr2` `.cr3` `.nef` `.arw` `.dng` `.raf` `.orf` `.rw2` | `Year/Month` folders |
| Other    | Everything else | Flat folder (no date sorting) |

System files (`.DS_Store`, `Thumbs.db`, `desktop.ini`, hidden files) are automatically ignored.

---

## Use Scenarios

### Migrate an old HDD to an SSD

```bash
# macOS
python3 photo_organizer.py --source '/Volumes/OldHDD' --dest /Volumes/SSD/Media --dry-run
python3 photo_organizer.py --source '/Volumes/OldHDD' --dest /Volumes/SSD/Media

# Windows
python photo_organizer.py --source "F:\" --dest "E:\Media" --dry-run
python photo_organizer.py --source "F:\" --dest "E:\Media"
```

### Reorganize a messy drive in-place

```bash
# macOS
python3 photo_organizer.py --reorganize --dest '/Volumes/MyDrive'

# Windows
python photo_organizer.py --reorganize --dest "D:\Photos"
```

### Merge photos from multiple sources

Run the script once per source — duplicates across runs are caught automatically:

```bash
# macOS
python3 photo_organizer.py --source /Volumes/USBStick/DCIM --dest ~/Pictures/Organized
python3 photo_organizer.py --source ~/OldBackup/Photos --dest ~/Pictures/Organized

# Windows
python photo_organizer.py --source "G:\DCIM" --dest "C:\Users\You\Pictures\Organized"
python photo_organizer.py --source "D:\OldBackup\Photos" --dest "C:\Users\You\Pictures\Organized"
```

### Quick scan of a drive

See what's on a drive without committing to anything:

```bash
# macOS
python3 photo_organizer.py --source '/Volumes/OldDrive' --dry-run

# Windows
python photo_organizer.py --source "F:\" --dry-run
```

---

## Quick Reference

| Action | Command |
|--------|---------|
| Copy A → B | `--source A --dest B` |
| Move A → B | `--source A --dest B --move` |
| Reorganize B | `--reorganize --dest B` |
| Preview | Add `--dry-run` to any command |
| Quick scan | `--source A --dry-run` |
| Custom log | Add `--log-file /path/to/log.txt` |

> **Tip:** Always run with `--dry-run` first before doing the real thing.

## License

MIT
