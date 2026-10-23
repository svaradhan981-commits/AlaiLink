
import requests
from pathlib import Path
from urllib.parse import urlparse, unquote, urljoin
from bs4 import BeautifulSoup

OUTPUT_DIR = Path("data/raw")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AlaiLinkResearch/1.0)"
}

def download_pdf(url):
    try:
        with requests.get(
            url,
            headers=HEADERS,
            timeout=30,
            stream=True
        ) as response:

            if response.status_code in (401, 403, 429):
                print(f"BLOCKED ({response.status_code}): {url}")
                return

            response.raise_for_status()

            filename = Path(
                unquote(urlparse(url).path)
            ).name

            # Handle URLs where the PDF filename is missing
            if not filename or not filename.lower().endswith(".pdf"):
                print(f"SKIP (not a direct PDF URL): {url}")
                return

            destination = OUTPUT_DIR / filename

            if destination.exists():
                print(f"SKIP (already have): {destination}")
                return

            first_chunk = next(
                response.iter_content(chunk_size=8192), b""
            )

            if not first_chunk.startswith(b"%PDF-"):
                print(f"SKIP (response is not a PDF): {url}")
                return

            with destination.open("wb") as file:
                file.write(first_chunk)

                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        file.write(chunk)

            print(
                f"saved {destination} "
                f"{destination.stat().st_size} bytes"
            )

    except requests.RequestException as error:
        print(f"FAILED: {url} — {error}")


def find_pdf_links(page_url):
    try:
        response = requests.get(
            page_url,
            headers=HEADERS,
            timeout=30
        )

        if response.status_code in (401, 403, 429):
            print(f"BLOCKED ({response.status_code}): {page_url}")
            return

        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        pdf_links = set()

        for link in soup.find_all("a", href=True):
            pdf_url = urljoin(page_url, link["href"])
            parsed = urlparse(pdf_url)

            if parsed.scheme not in ("http", "https"):
                continue

            if parsed.path.lower().endswith(".pdf"):
                pdf_links.add(pdf_url)

        print(f"Found {len(pdf_links)} PDF links: {page_url}")

        for pdf_url in sorted(pdf_links):
            download_pdf(pdf_url)

    except requests.RequestException as error:
        print(f"FAILED to read webpage: {page_url} — {error}")


def main():
    urls_file = Path("urls.txt")

    if not urls_file.exists():
        print("ERROR: urls.txt not found in project root.")
        return

    urls = [
        line.strip()
        for line in urls_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    if not urls:
        print("ERROR: Add website URLs to urls.txt.")
        return

    for url in urls:
        if urlparse(url).path.lower().endswith(".pdf"):
            download_pdf(url)
        else:
            find_pdf_links(url)


if __name__ == "__main__":
    main()
