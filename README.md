# Fast Media Downloader

A high-performance, asynchronous media downloader with a graphical user interface built in Python.  
It can download multiple media files simultaneously from direct URLs or by scanning static web pages.

---

## What kinds of links work

### Direct media file URLs
Paste the direct URL to any supported file — it is downloaded immediately:

```
https://example.com/photo.jpg
https://cdn.site.com/video.mp4
https://files.example.com/song.mp3
```

**Supported formats:** `.jpg` `.jpeg` `.png` `.gif` `.webp` `.bmp` `.mp4` `.avi` `.mov` `.m4v` `.mkv` `.webm` `.mp3` `.wav` `.flac` `.aac` `.ogg`

### HTML page URLs
Paste the URL of a static web page — the tool scans its HTML and downloads every media file it finds:

```
https://example.com/gallery
https://mysite.com/photos-page
```

It detects media inside `<img>`, `<video>`, `<source>`, and `<a>` tags.

---

## What does NOT work

| Not supported | Why |
|---|---|
| YouTube, Instagram, TikTok, Twitter/X, Facebook | Media is loaded by JavaScript, not in plain HTML. Use [yt-dlp](https://github.com/yt-dlp/yt-dlp) instead. |
| Pages that require login | The tool sends no cookies or credentials. |
| JavaScript-rendered pages (React, Vue, etc.) | Only the raw HTML is read — dynamic content is invisible to the scraper. |
| Magnet links / torrents | Not a supported protocol. |

---

## Features

- Asynchronous downloading for high performance
- Graphical user interface
- Supports both direct media links and static webpage scanning
- Cancel button to stop downloads at any time
- Retry with exponential backoff on failure
- Progress bar with file count and ETA
- Scrollable log panel showing every download result
- Skips files that already exist; renames on collision
- Accepts one URL per line, comma-separated, or from a `.txt` file

---

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/fast-media-downloader.git
cd fast-media-downloader
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

```bash
python fast_media_downloader.py
```

1. Paste URLs in the text box (one per line or comma-separated), or load a `.txt` file
2. Click **Start Download** and choose a destination folder
3. Watch the log panel for live results; click **Cancel** to stop at any time

## Requirements

- Python 3.10 or higher
- aiohttp
- aiofiles
- beautifulsoup4
- lxml
- tkinter (included with standard Python on Windows and macOS)

## Configuration

Constants at the top of `fast_media_downloader.py`:

| Constant | Default | Description |
|---|---|---|
| `MAX_CONCURRENT` | `20` | Max simultaneous connections total |
| `MAX_PER_HOST` | `5` | Max simultaneous connections per host |
| `MAX_RETRIES` | `3` | Retry attempts per file |
| `CHUNK_SIZE` | `65536` | Download chunk size in bytes |
| `CONNECT_TIMEOUT` | `30` | Seconds before a connection attempt fails |
| `READ_TIMEOUT` | `60` | Seconds of inactivity before a read fails |

## Disclaimer

This tool is for personal and educational use only. Always respect a website's terms of service and `robots.txt` before downloading its content.
