import os
import asyncio
import aiohttp
import aiofiles
import time
from bs4 import BeautifulSoup
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from urllib.parse import unquote, quote, urlparse
import threading

MEDIA_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp',
    '.mp4', '.avi', '.mov', '.m4v', '.mkv', '.webm',
    '.mp3', '.wav', '.flac', '.aac', '.ogg',
}
CHUNK_SIZE = 65536      # 64 KB
MAX_CONCURRENT = 20
MAX_PER_HOST = 5
MAX_RETRIES = 3
CONNECT_TIMEOUT = 30
READ_TIMEOUT = 60

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': '*/*',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
}


def safe_encode_url(url: str) -> str:
    """Re-encode URL path without double-encoding existing %XX sequences."""
    parsed = urlparse(url)
    encoded_path = quote(unquote(parsed.path), safe='/:@!$&\'()*+,;=')
    return parsed._replace(path=encoded_path).geturl()


def unique_path(file_path: str) -> str:
    """Return a unique file path by appending a counter suffix if needed."""
    if not os.path.exists(file_path):
        return file_path
    base, ext = os.path.splitext(file_path)
    counter = 1
    while os.path.exists(f"{base}_{counter}{ext}"):
        counter += 1
    return f"{base}_{counter}{ext}"


def resolve_url(raw: str, page_url: str) -> str | None:
    """Resolve relative, protocol-relative, and absolute URLs."""
    raw = raw.strip()
    if raw.startswith('//'):
        scheme = urlparse(page_url).scheme
        return f"{scheme}:{raw}"
    if raw.startswith('/'):
        p = urlparse(page_url)
        return f"{p.scheme}://{p.netloc}{raw}"
    if raw.startswith(('http://', 'https://')):
        return raw
    return None  # skip javascript:, data:, mailto:, etc.


def is_media_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in MEDIA_EXTENSIONS)


class AsyncDownloadManager:
    def __init__(self, root, progress_var, status_var, log_callback):
        self.root = root
        self.progress_var = progress_var
        self.status_var = status_var
        self._log = log_callback
        self.total_files = 0
        self.downloaded_files = 0
        self._lock = asyncio.Lock()
        self._cancel = asyncio.Event()
        self._start_time: float | None = None

    def request_cancel(self):
        self._cancel.set()

    async def download_file(self, session: aiohttp.ClientSession, url: str, file_path: str) -> bool:
        if self._cancel.is_set():
            return False

        if os.path.exists(file_path):
            self._log(f"[skip] {os.path.basename(file_path)}")
            async with self._lock:
                self.downloaded_files += 1
                self._update_ui()
            return True

        tmp_path = file_path + ".tmp"

        for attempt in range(MAX_RETRIES):
            if self._cancel.is_set():
                return False
            try:
                timeout = aiohttp.ClientTimeout(connect=CONNECT_TIMEOUT, sock_read=READ_TIMEOUT)
                async with session.get(safe_encode_url(url), headers=HEADERS, timeout=timeout) as resp:
                    if resp.status not in (200, 206):
                        self._log(f"[error] HTTP {resp.status}: {url}")
                        return False

                    total_size = int(resp.headers.get('content-length', 0))
                    downloaded_size = 0
                    os.makedirs(os.path.dirname(file_path) or '.', exist_ok=True)

                    async with aiofiles.open(tmp_path, 'wb') as f:
                        async for chunk in resp.content.iter_chunked(CHUNK_SIZE):
                            if self._cancel.is_set():
                                self._cleanup(tmp_path)
                                return False
                            await f.write(chunk)
                            downloaded_size += len(chunk)

                    if total_size > 0 and downloaded_size < total_size:
                        raise aiohttp.ClientError(
                            f"Incomplete download: {downloaded_size}/{total_size} bytes"
                        )

                    final_path = unique_path(file_path)
                    os.replace(tmp_path, final_path)  # atomic rename

                    async with self._lock:
                        self.downloaded_files += 1
                        self._update_ui()

                    self._log(f"[ok] {os.path.basename(final_path)}")
                    return True

            except (aiohttp.ClientError, ConnectionResetError, asyncio.TimeoutError) as e:
                self._cleanup(tmp_path)
                if attempt < MAX_RETRIES - 1:
                    wait = 2 ** attempt
                    self._log(f"[retry {attempt + 1}/{MAX_RETRIES}] {os.path.basename(file_path)}: {e}")
                    await asyncio.sleep(wait)
                else:
                    self._log(f"[failed] {os.path.basename(file_path)}: {e}")
                    return False
            except Exception as e:
                self._cleanup(tmp_path)
                self._log(f"[error] {os.path.basename(file_path)}: {e}")
                return False

        return False

    def _cleanup(self, tmp_path: str):
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass

    def _update_ui(self):
        if self.total_files == 0:
            return
        progress = (self.downloaded_files / self.total_files) * 100
        elapsed = time.monotonic() - self._start_time if self._start_time else 0
        speed = self.downloaded_files / elapsed if elapsed > 0 else 0
        remaining = (self.total_files - self.downloaded_files) / speed if speed > 0 else 0
        eta = f" | ETA {remaining:.0f}s" if remaining > 0 else ""
        status = f"{self.downloaded_files}/{self.total_files} files{eta}"
        self.root.after(0, lambda p=progress, s=status: (
            self.progress_var.set(p),
            self.status_var.set(s),
        ))

    async def process_url(self, session: aiohttp.ClientSession, url: str) -> list[tuple[str, str]]:
        url = url.strip()
        if not url.startswith(('http://', 'https://')):
            self._log(f"[skip] Invalid URL: {url}")
            return []

        if is_media_url(url):
            filename = unquote(os.path.basename(urlparse(url).path))
            return [(url, filename)] if filename else []

        try:
            timeout = aiohttp.ClientTimeout(connect=CONNECT_TIMEOUT, sock_read=READ_TIMEOUT)
            async with session.get(url, headers=HEADERS, timeout=timeout) as resp:
                if resp.status != 200:
                    self._log(f"[error] Fetch failed ({resp.status}): {url}")
                    return []
                if 'text/html' not in resp.headers.get('content-type', ''):
                    self._log(f"[skip] Not HTML: {url}")
                    return []
                html = await resp.text()
        except Exception as e:
            self._log(f"[error] Fetch {url}: {e}")
            return []

        soup = BeautifulSoup(html, 'lxml')
        found: list[tuple[str, str]] = []
        seen: set[str] = set()

        selectors = 'img[src], video[src], video source[src], source[src], a[href]'
        for el in soup.select(selectors):
            raw = el.get('src') or el.get('href')
            if not raw or not isinstance(raw, str):
                continue
            resolved = resolve_url(raw, url)
            if not resolved or resolved in seen or not is_media_url(resolved):
                continue
            seen.add(resolved)
            filename = unquote(os.path.basename(urlparse(resolved).path))
            if filename:
                found.append((resolved, filename))

        return found


async def download_all(urls: list[str], folder: str, manager: AsyncDownloadManager) -> int:
    conn = aiohttp.TCPConnector(
        limit=MAX_CONCURRENT,
        limit_per_host=MAX_PER_HOST,
        force_close=False,
        enable_cleanup_closed=True,
    )
    async with aiohttp.ClientSession(connector=conn) as session:
        # Phase 1: discover media URLs from all input URLs in parallel
        scan_tasks = [manager.process_url(session, u) for u in urls]
        scan_results = await asyncio.gather(*scan_tasks)
        all_media = [item for sublist in scan_results for item in sublist]

        # Deduplicate by URL while preserving order
        seen: set[str] = set()
        unique_media = []
        for url, filename in all_media:
            if url not in seen:
                seen.add(url)
                unique_media.append((url, filename))

        manager.total_files = len(unique_media)
        manager._start_time = time.monotonic()

        if not unique_media:
            manager._log("No media files found.")
            return 0

        manager._log(f"Found {len(unique_media)} files to download.")

        # Phase 2: download all files concurrently (connector handles rate limiting)
        dl_tasks = [
            manager.download_file(session, url, os.path.join(folder, filename))
            for url, filename in unique_media
        ]
        results = await asyncio.gather(*dl_tasks)
        return sum(1 for r in results if r)


class MediaDownloaderGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Fast Media Downloader")
        self.root.resizable(True, True)
        self.root.minsize(540, 420)
        self._manager: AsyncDownloadManager | None = None
        self._setup_gui()

    def _setup_gui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        frame = ttk.Frame(self.root, padding=12)
        frame.grid(row=0, column=0, sticky='nsew')
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)  # log area expands

        # --- URL input ---
        header_frame = ttk.Frame(frame)
        header_frame.grid(row=0, column=0, sticky='ew', pady=(0, 2))
        header_frame.columnconfigure(0, weight=1)

        ttk.Label(header_frame, text="Enter links (one per line, or comma-separated):").grid(
            row=0, column=0, sticky='w')
        ttk.Button(header_frame, text="ⓘ What links work?", command=self._show_link_info).grid(
            row=0, column=1, sticky='e')

        ttk.Label(
            frame,
            text="✔ Direct media URLs  ✔ Static HTML pages    ✘ YouTube/Instagram/TikTok  ✘ Pages needing login",
            foreground='gray',
            font=('TkDefaultFont', 8),
        ).grid(row=0, column=0, sticky='e', pady=(0, 2))

        url_frame = ttk.Frame(frame)
        url_frame.grid(row=1, column=0, sticky='ew', pady=(4, 8))
        url_frame.columnconfigure(0, weight=1)

        self._links_text = tk.Text(url_frame, height=6, width=60, wrap='word')
        url_scroll = ttk.Scrollbar(url_frame, command=self._links_text.yview)
        self._links_text.configure(yscrollcommand=url_scroll.set)
        self._links_text.grid(row=0, column=0, sticky='ew')
        url_scroll.grid(row=0, column=1, sticky='ns')

        # --- File input ---
        file_frame = ttk.Frame(frame)
        file_frame.grid(row=3, column=0, sticky='ew', pady=(0, 10))
        file_frame.columnconfigure(1, weight=1)

        ttk.Label(file_frame, text="OR load from file:").grid(row=0, column=0, padx=(0, 6))
        self._file_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self._file_var).grid(row=0, column=1, sticky='ew')
        ttk.Button(file_frame, text="Browse…", command=self._select_file).grid(row=0, column=2, padx=(4, 0))

        # --- Buttons ---
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=4, column=0, pady=6)

        self._start_btn = ttk.Button(btn_frame, text="Start Download", command=self._start_download)
        self._start_btn.grid(row=0, column=0, padx=4)
        self._cancel_btn = ttk.Button(btn_frame, text="Cancel", command=self._cancel, state='disabled')
        self._cancel_btn.grid(row=0, column=1, padx=4)

        # --- Progress ---
        self._progress_var = tk.DoubleVar()
        ttk.Progressbar(frame, variable=self._progress_var, maximum=100).grid(
            row=5, column=0, sticky='ew', pady=(6, 2))

        self._status_var = tk.StringVar(value="Ready")
        ttk.Label(frame, textvariable=self._status_var, anchor='w').grid(
            row=6, column=0, sticky='ew')

        # --- Log ---
        ttk.Label(frame, text="Log:").grid(row=7, column=0, sticky='w', pady=(10, 2))

        log_frame = ttk.Frame(frame)
        log_frame.grid(row=8, column=0, sticky='nsew')
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        frame.rowconfigure(8, weight=1)

        self._log_text = tk.Text(
            log_frame, height=8, state='disabled', wrap='word',
            bg='#1e1e1e', fg='#d4d4d4', font=('Consolas', 9),
            relief='flat', insertbackground='white',
        )
        log_scroll = ttk.Scrollbar(log_frame, command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=log_scroll.set)
        self._log_text.grid(row=0, column=0, sticky='nsew')
        log_scroll.grid(row=0, column=1, sticky='ns')

    def _show_link_info(self):
        msg = (
            "WHAT WORKS\n"
            "──────────────────────────────────────\n"
            "✔  Direct media file URLs\n"
            "     e.g. https://example.com/photo.jpg\n"
            "     Supported: jpg jpeg png gif webp bmp\n"
            "                mp4 avi mov m4v mkv webm\n"
            "                mp3 wav flac aac ogg\n\n"
            "✔  Static HTML page URLs\n"
            "     The page is scanned for media found\n"
            "     in <img>, <video>, <source>, <a> tags.\n\n"
            "WHAT DOES NOT WORK\n"
            "──────────────────────────────────────\n"
            "✘  YouTube, Instagram, TikTok, Twitter/X\n"
            "     (media loaded by JavaScript — use yt-dlp)\n\n"
            "✘  Pages that require login / cookies\n\n"
            "✘  JavaScript-rendered pages (React, Vue…)\n"
            "     (only raw HTML is read)\n\n"
            "✘  Magnet links or torrents"
        )
        messagebox.showinfo("Supported link types", msg)

    def _log(self, msg: str):
        def _append():
            self._log_text.configure(state='normal')
            self._log_text.insert('end', msg + '\n')
            self._log_text.see('end')
            self._log_text.configure(state='disabled')
        self.root.after(0, _append)

    def _select_file(self):
        path = filedialog.askopenfilename(
            title="Select file with links",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if path:
            self._file_var.set(path)

    def _read_links(self) -> list[str]:
        raw = self._links_text.get('1.0', 'end')
        links = [p.strip() for line in raw.replace(',', '\n').splitlines() for p in [line.strip()] if p]

        if self._file_var.get():
            for enc in ('utf-8', 'utf-8-sig', 'latin-1', 'cp1252'):
                try:
                    with open(self._file_var.get(), encoding=enc) as f:
                        content = f.read()
                    file_links = [p.strip() for line in content.replace(',', '\n').splitlines()
                                  for p in [line.strip()] if p]
                    links.extend(file_links)
                    break
                except UnicodeDecodeError:
                    continue
                except OSError as e:
                    messagebox.showerror("Error", f"Cannot read file: {e}")
                    return []

        # Deduplicate while preserving order
        seen: set[str] = set()
        result = []
        for link in links:
            if link not in seen:
                seen.add(link)
                result.append(link)
        return result

    def _start_download(self):
        links = self._read_links()
        if not links:
            messagebox.showwarning("Warning", "Please enter at least one link.")
            return

        folder = filedialog.askdirectory(title="Choose destination folder")
        if not folder:
            return

        self._start_btn.config(state='disabled')
        self._cancel_btn.config(state='normal')
        self._progress_var.set(0)
        self._status_var.set("Scanning for media…")

        self._manager = AsyncDownloadManager(
            self.root,
            progress_var=self._progress_var,
            status_var=self._status_var,
            log_callback=self._log,
        )

        threading.Thread(
            target=lambda: asyncio.run(self._run(links, folder)),
            daemon=True,
        ).start()

    def _cancel(self):
        if self._manager:
            self._manager.request_cancel()
            self._status_var.set("Cancelling…")

    async def _run(self, links: list[str], folder: str):
        assert self._manager is not None
        try:
            n = await download_all(links, folder, self._manager)
            cancelled = self._manager._cancel.is_set()
            msg = f"Cancelled. {n} file(s) saved." if cancelled else f"Done! {n} file(s) downloaded."
            self.root.after(0, lambda: messagebox.showinfo("Complete", msg))
            self.root.after(0, lambda: self._status_var.set(msg))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
        finally:
            self.root.after(0, lambda: self._start_btn.config(state='normal'))
            self.root.after(0, lambda: self._cancel_btn.config(state='disabled'))

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = MediaDownloaderGUI()
    app.run()
