# Fast Media Downloader

A high-performance, asynchronous media downloader with a graphical user interface built in Python. This tool can efficiently download multiple media files (images, videos) simultaneously from web pages or direct URLs.

## Features

- Asynchronous downloading for high performance
- Graphical user interface for easy use
- Supports both direct media links and webpage scanning
- Multiple retry attempts with exponential backoff
- Progress tracking with percentage and file counts
- Supports comma-separated links or text file input
- Handles connection drops and timeouts gracefully
- Concurrent downloads with configurable limits

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

Run the program:
```bash
python fast_downloader.py
```

You can provide input in two ways:
1. Enter URLs directly in the text field (comma-separated)
2. Load URLs from a text file

Then:
1. Click "Start Download"
2. Choose a destination folder
3. Wait for the downloads to complete

## Requirements

- Python 3.7 or higher
- aiohttp
- aiofiles
- beautifulsoup4
- lxml
- tkinter (usually comes with Python)

## Configuration

You can modify these parameters in the code:
- `max_retries`: Number of retry attempts for failed downloads (default: 3)
- `semaphore`: Maximum concurrent downloads (default: 50)
- `limit_per_host`: Maximum concurrent connections per host (default: 10)

## Error Handling

The program includes:
- Automatic retry with exponential backoff
- Connection timeout handling
- Incomplete download detection
- Rate limiting management

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Uses aiohttp for async HTTP requests
- Uses Beautiful Soup 4 for HTML parsing
- Uses tkinter for the GUI

## Disclaimer

This tool is for educational purposes only. Make sure to respect websites' terms of service and robots.txt when downloading content.
