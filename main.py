import argparse
import os.path
import subprocess
import sys
from datetime import datetime
from playwright.sync_api import sync_playwright


def login(args):
    print("Opening browser for Fansly login...", flush=True)
    print("Please log in to Fansly in the browser window that opens.", flush=True)
    print("After logging in, press Enter here to save the session.", flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://fansly.com", wait_until="load")

        input("Press Enter after you have logged in...")

        context.storage_state(path=args.storage_state)
        print(f"Authentication state saved to {args.storage_state}", flush=True)

        page.close()
        browser.close()


def capture_stream(context, url, monitor_time):
    """Navigate to stream URL, capture m3u8 request, return (m3u8_url, cookie_string)."""
    page = context.new_page()
    captured_urls = []

    def handle_request(request):
        if ".m3u8" in request.url and "analytics" not in request.url:
            print(f"[FOUND STREAM] {request.url}", flush=True)
            captured_urls.append(request.url)

    page.on("request", handle_request)

    print(f"Navigating to {url}...", flush=True)
    try:
        page.goto(url, wait_until="load", timeout=60000)
    except Exception as e:
        print(f"[WARNING] Page load took a long time or timed out: {e}", file=sys.stderr, flush=True)

    print(f"Monitoring background network traffic for up to {monitor_time} seconds...", flush=True)
    for _ in range(monitor_time):
        if captured_urls:
            break
        page.wait_for_timeout(1000)

    if not captured_urls:
        print("\n[ERROR] No m3u8 URL captured.", file=sys.stderr, flush=True)
        page.close()
        sys.exit(1)

    final_m3u8 = captured_urls[-1]
    cookies = context.cookies()
    cookie_string = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
    page.close()

    return final_m3u8, cookie_string


def record_with_cdp(args):
    """Record using an existing browser via CDP."""
    with sync_playwright() as p:
        print(f"Connecting to your running Brave instance on {args.cdp_url}...", flush=True)
        try:
            browser = p.chromium.connect_over_cdp(args.cdp_url)
        except Exception as e:
            print(f"\n[ERROR] Could not connect to Brave. Is it running with --remote-debugging-port=9222?", file=sys.stderr, flush=True)
            print(f"Details: {e}", file=sys.stderr, flush=True)
            sys.exit(1)

        context = browser.contexts[0]
        return capture_stream(context, args.url, args.monitor_time)


def record_with_storage(args):
    """Record using a headless browser with saved authentication state."""
    with sync_playwright() as p:
        print("Starting headless browser with saved authentication state...", flush=True)
        try:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(storage_state=args.storage_state)
        except Exception as e:
            print(f"\n[ERROR] Could not load storage state from {args.storage_state}", file=sys.stderr, flush=True)
            print("Run with --login to re-authenticate.", file=sys.stderr, flush=True)
            print(f"Details: {e}", file=sys.stderr, flush=True)
            sys.exit(1)

        try:
            return capture_stream(context, args.url, args.monitor_time)
        finally:
            context.close()
            browser.close()


def run():
    parser = argparse.ArgumentParser(description="Fansly stream recorder")
    parser.add_argument("--url", help="Stream URL to record")
    parser.add_argument("-o", "--output", help="Output file path (default: live_recording_<timestamp>.ts)")
    parser.add_argument("--login", action="store_true", help="Interactive login to save authentication state")
    parser.add_argument("--storage-state", default="fansly_auth.json", help="Path to saved auth state file (default: fansly_auth.json)")
    parser.add_argument("--cdp-url", default="http://localhost:9222", help="CDP URL for existing browser (default: http://localhost:9222)")
    parser.add_argument("--monitor-time", type=int, default=15, help="Seconds to wait for stream playlist (default: 15)")
    args = parser.parse_args()

    if args.login:
        login(args)
        return

    if not args.url:
        print("Error: --url is required for recording mode", file=sys.stderr, flush=True)
        sys.exit(1)

    output = args.output or f"live_recording_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ts"

    if os.path.exists(args.storage_state):
        print(f"Using saved authentication state from {args.storage_state}", flush=True)
        final_m3u8, cookie_string = record_with_storage(args)
    else:
        print(f"No saved authentication state found at {args.storage_state}", flush=True)
        final_m3u8, cookie_string = record_with_cdp(args)

    print(f"\nHanding stream link and active login session over to Streamlink...", flush=True)
    print(f"Recording to file: {output}", flush=True)
    print("Press Ctrl+C inside this terminal window to stop recording.", flush=True)

    streamlink_cmd = [
        "streamlink",
        f"hlsvariant://{final_m3u8}",
        "best",
        "-o", output,
        "--http-header", f"Cookie={cookie_string}",
        "--http-header", "User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ]

    try:
        result = subprocess.run(streamlink_cmd)
    except KeyboardInterrupt:
        print("\nRecording stopped by user. File saved.", flush=True)
    else:
        if result.returncode != 0:
            print(f"\n[ERROR] Streamlink exited with code {result.returncode}", file=sys.stderr, flush=True)
            sys.exit(result.returncode)


if __name__ == "__main__":
    run()
