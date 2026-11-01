
import time
import hashlib
import re
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag, unquote
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

URLS_FILE = Path("urls.txt")
PAGES_DIR = Path("data/raw/pages")
PDF_DIR = Path("data/raw/pdfs")

PAGES_DIR.mkdir(parents=True, exist_ok=True)
PDF_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "AlaiLinkResearchBot/1.0 (educational research)"
}

DELAY = 0.7
TIMEOUT = 30

session = requests.Session()
session.headers.update(HEADERS)
robots_cache = {}
visited = set()


def clean_url(url):
    url, _ = urldefrag(url)
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None

    return url


def allowed_by_robots(url):
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    if origin not in robots_cache:
        parser = RobotFileParser()
        robots_url = urljoin(origin, "/robots.txt")

        try:
            response = session.get(robots_url, timeout=TIMEOUT)

            if response.status_code == 404:
                parser.parse(["User-agent: *", "Allow: /"])
            elif response.ok:
                parser.parse(response.text.splitlines())
            else:
                parser.parse(["User-agent: *", "Disallow: /"])
                print(f"Cannot verify robots.txt: {robots_url}")

        except requests.RequestException:
            parser.parse(["User-agent: *", "Disallow: /"])
            print(f"Cannot access robots.txt: {robots_url}")

        robots_cache[origin] = parser

    return robots_cache[origin].can_fetch(
        HEADERS["User-Agent"], url
    )


def filename_for(title, url, suffix):
    title = unquote(title or "page")
    title = re.sub(r"[^\w.-]+", "_", title, flags=re.UNICODE)
    title = title.strip("._")[:80] or "page"
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]
    return f"{title}_{digest}{suffix}"


def download_pdf(url, response):
    name = Path(unquote(urlparse(url).path)).stem
    if not name:
        name = "document"

    destination = PDF_DIR / filename_for(name, url, ".pdf")

    if destination.exists():
        print(f"SKIP (already have): {destination}")
        return

    first_bytes = b""

    try:
        with destination.open("wb") as output:
            for chunk in response.iter_content(65536):
                if chunk:
                    if not first_bytes:
                        first_bytes = chunk[:8]
                    output.write(chunk)

        if not first_bytes.startswith(b"%PDF-"):
            destination.unlink(missing_ok=True)
            print(f"SKIP (not a valid PDF): {url}")
            return

        print(f"SAVED PDF: {destination}")

    except OSError as error:
        destination.unlink(missing_ok=True)
        print(f"FAILED to save PDF: {error}")


def extract_text(soup):
    for element in soup(
        ["script", "style", "noscript", "svg", "nav", "footer"]
    ):
        element.decompose()

    main = soup.find("main") or soup.find("article") or soup.body or soup

    return "\n".join(
        line.strip()
        for line in main.get_text("\n").splitlines()
        if line.strip()
    )


def crawl(seed_urls):
    queue = deque()
    allowed_hosts = set()

    for seed in seed_urls:
        seed = clean_url(seed)
        if seed:
            queue.append(seed)
            allowed_hosts.add(urlparse(seed).netloc.lower())

    while queue:
        url = queue.popleft()

        if url in visited:
            continue

        visited.add(url)

        if not allowed_by_robots(url):
            print(f"SKIP (robots.txt): {url}")
            continue

        try:
            with session.get(
                url,
                timeout=TIMEOUT,
                stream=True,
                allow_redirects=True,
            ) as response:

                if response.status_code in (401, 403, 429):
                    print(f"BLOCKED ({response.status_code}): {url}")
                    continue

                response.raise_for_status()

                content_type = response.headers.get(
                    "Content-Type", ""
                ).lower()

                final_url = response.url

                is_pdf = (
                    "application/pdf" in content_type
                    or urlparse(final_url).path.lower().endswith(".pdf")
                )

                if is_pdf:
                    download_pdf(final_url, response)
                    time.sleep(DELAY)
                    continue

                if (
                    "text/html" not in content_type
                    and "application/xhtml+xml" not in content_type
                ):
                    print(f"SKIP (unsupported content): {url}")
                    continue

                html = response.text

            soup = BeautifulSoup(html, "html.parser")
            title = (
                soup.title.get_text(" ", strip=True)
                if soup.title else urlparse(final_url).path
            )

            text = extract_text(soup)

            if text:
                output_path = PAGES_DIR / filename_for(
                    title, final_url, ".txt"
                )

                output_path.write_text(
                    f"TITLE: {title}\n"
                    f"SOURCE_URL: {final_url}\n\n"
                    f"{text}\n",
                    encoding="utf-8",
                )

                print(f"SAVED PAGE: {output_path}")

            # Discover links on the supplied website hosts.
            for anchor in soup.find_all("a", href=True):
                next_url = clean_url(
                    urljoin(final_url, anchor["href"])
                )

                if not next_url:
                    continue

                host = urlparse(next_url).netloc.lower()

                if host in allowed_hosts and next_url not in visited:
                    queue.append(next_url)

        except requests.RequestException as error:
            print(f"FAILED: {url} — {error}")
        except OSError as error:
            print(f"FAILED to save content: {url} — {error}")

        time.sleep(DELAY)

    print("\nCrawling completed!")
    print(f"URLs visited: {len(visited)}")
    print(f"Webpage text: {PAGES_DIR}")
    print(f"PDF documents: {PDF_DIR}")


def main():
    if not URLS_FILE.exists():
        print("ERROR: urls.txt not found in project root.")
        return

    urls = [
        line.strip()
        for line in URLS_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    if not urls:
        print("ERROR: Add website URLs to urls.txt.")
        return

    crawl(urls)


if __name__ == "__main__":
    main()
