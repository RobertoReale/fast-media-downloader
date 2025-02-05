import os
import asyncio
import aiohttp
import aiofiles
from bs4 import BeautifulSoup
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from urllib.parse import unquote, quote, urlparse
import threading

class AsyncDownloadManager:
    def __init__(self, root):
        self.root = root
        self.progress_var = tk.DoubleVar()
        self.status_var = tk.StringVar()
        self.total_files = 0
        self.downloaded_files = 0
        self.semaphore = asyncio.Semaphore(50)  # Limit concurrent connections
        
    async def download_file(self, session, url, file_path, max_retries=3):
        # First check if file exists
        if os.path.exists(file_path):
            print(f"File already exists: {file_path}")
            self.downloaded_files += 1
            progress = (self.downloaded_files / self.total_files) * 100
            self.root.after(0, lambda: self.progress_var.set(progress))
            self.root.after(0, lambda: self.status_var.set(
                f"Skipped existing file. Progress: {self.downloaded_files}/{self.total_files} files"))
            return True

        for attempt in range(max_retries):
            try:
                async with self.semaphore:  # Control concurrent downloads
                    parsed = urlparse(url)
                    encoded_path = quote(parsed.path.encode('utf-8'))
                    encoded_url = parsed._replace(path=encoded_path).geturl()
                    
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                        'Connection': 'keep-alive',
                        'Accept': '*/*'
                    }
                    
                    timeout = aiohttp.ClientTimeout(total=None, connect=60, sock_read=60)
                    async with session.get(encoded_url, headers=headers, timeout=timeout) as response:
                        if response.status == 200:
                            os.makedirs(os.path.dirname(file_path), exist_ok=True)
                            
                            # Get total size for resuming
                            total_size = int(response.headers.get('content-length', 0))
                            downloaded_size = 0
                            
                            async with aiofiles.open(file_path, 'wb') as f:
                                async for chunk in response.content.iter_chunked(32768):
                                    if chunk:  # filter out keep-alive chunks
                                        await f.write(chunk)
                                        downloaded_size += len(chunk)
                                
                                # Verify complete download
                                if total_size > 0 and downloaded_size < total_size:
                                    raise aiohttp.ClientError(f"Incomplete download: {downloaded_size}/{total_size} bytes")
                                
                            self.downloaded_files += 1
                            progress = (self.downloaded_files / self.total_files) * 100
                            self.root.after(0, lambda: self.progress_var.set(progress))
                            self.root.after(0, lambda: self.status_var.set(
                                f"Downloaded {self.downloaded_files}/{self.total_files} files"))
                            print(f"Successfully downloaded: {url}")
                            return True
                    return False
                    
            except (aiohttp.ClientError, ConnectionResetError, asyncio.TimeoutError) as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    print(f"Attempt {attempt + 1} failed for {url}: {e}. Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"Failed to download {url} after {max_retries} attempts: {e}")
                    return False
            except Exception as e:
                print(f"Unexpected error downloading {url}: {e}")
                return False

    async def process_url(self, session, url):
        try:
            # Check if it's a direct media file
            if any(url.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.mp4', '.avi', '.mov', '.m4v']):
                return [(url, os.path.basename(urlparse(url).path))]

            # If not a direct media file, try to parse as HTML
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    print(f"Failed to fetch {url}: Status {response.status}")
                    return []
                
                if not response.headers.get('content-type', '').startswith('text/html'):
                    print(f"Not an HTML page: {url}")
                    return []
                    
                content = await response.text()
                soup = BeautifulSoup(content, 'lxml')
                media_urls = []

                # Find media in various HTML elements
                for element in soup.select('img[src], video source[src], a[href]'):
                    media_url = element.get('src') or element.get('href')
                    if not media_url:
                        continue
                        
                    if not media_url.startswith(('http://', 'https://')):
                        media_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}{media_url}"
                        
                    if any(media_url.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.mp4', '.avi', '.mov']):
                        filename = os.path.basename(urlparse(media_url).path)
                        if filename:
                            media_urls.append((media_url, filename))

                return media_urls
        except aiohttp.ClientError as e:
            print(f"Network error processing {url}: {e}")
            return []
        except Exception as e:
            print(f"Error processing {url}: {e}")
            return []

async def download_all(urls, download_folder, download_manager):
    # Configure connection settings
    conn = aiohttp.TCPConnector(
        limit=50,  # Maximum number of concurrent connections
        limit_per_host=10,  # Maximum number of concurrent connections per host
        force_close=False,  # Keep connections alive
        enable_cleanup_closed=True  # Clean up closed connections
    )
    
    timeout = aiohttp.ClientTimeout(
        total=None,  # No total timeout
        connect=30,  # 30 seconds connect timeout
        sock_read=30,  # 30 seconds read timeout
        sock_connect=30  # 30 seconds to establish connection
    )
    
    async with aiohttp.ClientSession(connector=conn, timeout=timeout) as session:
        # First gather all media URLs in parallel
        tasks = [download_manager.process_url(session, url.strip()) for url in urls if url.strip()]
        results = await asyncio.gather(*tasks)
        
        all_media_urls = [item for sublist in results for item in sublist]
        download_manager.total_files = len(all_media_urls)
        
        if download_manager.total_files == 0:
            return 0
            
        print(f"Found {download_manager.total_files} files to download")
        
        # Download all files in parallel
        tasks = [
            download_manager.download_file(
                session, 
                url, 
                os.path.join(download_folder, filename)
            ) 
            for url, filename in all_media_urls
        ]
        results = await asyncio.gather(*tasks)
        return sum(1 for r in results if r)

class MediaDownloaderGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Fast Media Downloader")
        self.setup_gui()

    def setup_gui(self):
        # Main frame
        self.frame = ttk.Frame(self.root, padding="10")
        self.frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Links entry
        ttk.Label(self.frame, text="Enter links (comma-separated):").grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 5))
        self.links_entry = ttk.Entry(self.frame, width=60)
        self.links_entry.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        # Separator
        ttk.Label(self.frame, text="OR").grid(
            row=2, column=0, columnspan=2, pady=5)

        # File selection
        self.file_path_var = tk.StringVar()
        self.file_entry = ttk.Entry(
            self.frame, textvariable=self.file_path_var, width=45)
        self.file_entry.grid(row=3, column=0, sticky=(tk.W, tk.E), padx=(0, 5))
        
        ttk.Button(self.frame, text="Choose File", command=self.select_file).grid(
            row=3, column=1, sticky=tk.E)

        # Download button
        self.download_button = ttk.Button(
            self.frame, text="Start Download", command=self.start_download)
        self.download_button.grid(
            row=4, column=0, columnspan=2, pady=10)

        # Progress frame (created when needed)
        self.progress_frame = None

    def select_file(self):
        file_path = filedialog.askopenfilename(
            title="Select text file with links",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if file_path:
            self.file_path_var.set(file_path)

    def read_links(self):
        links = []
        
        # Get links from entry
        entry_links = [link.strip() for link in self.links_entry.get().split(',')
                      if link.strip()]
        links.extend(entry_links)

        # Get links from file if specified
        if self.file_path_var.get():
            try:
                for encoding in ['utf-8', 'latin-1', 'cp1252']:
                    try:
                        with open(self.file_path_var.get(), 'r', encoding=encoding) as file:
                            file_links = [link.strip() for line in file.readlines()
                                        for link in line.split(',')
                                        if link.strip()]
                            links.extend(file_links)
                        break
                    except UnicodeDecodeError:
                        continue
            except Exception as e:
                messagebox.showerror("Error", f"Error reading file: {str(e)}")
                return []

        return links

    def create_progress_frame(self):
        if self.progress_frame:
            self.progress_frame.destroy()
            
        self.progress_frame = ttk.Frame(self.frame)
        self.progress_frame.grid(row=5, column=0, columnspan=2, pady=10, sticky='ew')
        
        self.progress_bar = ttk.Progressbar(
            self.progress_frame,
            variable=self.download_manager.progress_var,
            maximum=100
        )
        self.progress_bar.pack(fill='x', padx=5)
        
        self.status_label = ttk.Label(
            self.progress_frame,
            textvariable=self.download_manager.status_var
        )
        self.status_label.pack(pady=5)

    def start_download(self):
        links = self.read_links()
        
        if not links:
            messagebox.showwarning(
                "Warning",
                "Please enter links or choose a text file with links."
            )
            return

        download_folder = filedialog.askdirectory(
            title="Choose destination folder")
        if not download_folder:
            return

        self.download_button.config(state='disabled')
        self.download_manager = AsyncDownloadManager(self.root)
        self.create_progress_frame()

        def run_async():
            asyncio.run(self.process_downloads(links, download_folder))

        threading.Thread(target=run_async, daemon=True).start()

    async def process_downloads(self, links, download_folder):
        try:
            successful = await download_all(
                links, download_folder, self.download_manager)
            self.root.after(0, lambda: messagebox.showinfo(
                "Info", f"Download completed. Files downloaded: {successful}"))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror(
                "Error", f"Error during download: {str(e)}"))
        finally:
            self.root.after(0, lambda: self.download_button.config(state='normal'))
            self.root.after(0, lambda: self.progress_frame.destroy())

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = MediaDownloaderGUI()
    app.run()
