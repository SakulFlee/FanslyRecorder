import argparse
import subprocess
import time
import sys
from datetime import datetime
from playwright.sync_api import sync_playwright


def login(args):
    print("Opening browser for Fansly login...")
    print("Please log in to Fansly in the browser window that opens.")
    print("After logging in, press Enter here to save the session.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://fansly.com", wait_until="load")

        input("Press Enter after you have logged in...")

        context.storage_state(path=args.storage_state)
        print(f"Authentication state saved to {args.storage_state}")

        page.close()
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
        print("Error: --url is required for recording mode")
        sys.exit(1)

    output = args.output or f"live_recording_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ts"

    with sync_playwright() as p:
        print(f"Connecting to your running Brave instance on {args.cdp_url}...")

        try:
            browser = p.chromium.connect_over_cdp(args.cdp_url)
        except Exception as e:
            print(f"\n[ERROR] Could not connect to Brave. Is it running with --remote-debugging-port=9222?")
            print(f"Details: {e}")
            sys.exit(1)

        context = browser.contexts[0]
        page = context.new_page()

        captured_urls = []

        def handle_request(request):
            url = request.url
            if ".m3u8" in url and "analytics" not in url:
                print(f"[FOUND STREAM] {url}")
                captured_urls.append(url)

        page.on("request", handle_request)

        print(f"Navigating to {args.url}...")
        try:
            page.goto(args.url, wait_until="load", timeout=60000)
        except Exception as e:
            print(f"[WARNING] Page load took a long time or timed out: {e}")

        print(f"Monitoring background network traffic for {args.monitor_time} seconds...")
        time.sleep(args.monitor_time)

        if not captured_urls:
            print("\n[ERROR] No m3u8 URL captured.")
            print("Check your Brave window—did the stream fail to auto-play, or did a popup block it?")
            page.close()
            return

        final_m3u8 = captured_urls[-1]
        cookies = context.cookies()
        cookie_string = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        page.close()

    print(f"\nHanding stream link and active login session over to Streamlink...")
    print(f"Recording to file: {output}")
    print("Press Ctrl+C inside this terminal window to stop recording.")

    streamlink_cmd = [
        "streamlink",
        f"hlsvariant://{final_m3u8}",
        "best",
        "-o", output,
        "--http-header", f"Cookie={cookie_string}",
        "--http-header", "User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ]

    try:
        subprocess.run(streamlink_cmd)
    except KeyboardInterrupt:
        print("\nRecording stopped by user. File saved.")


if __name__ == "__main__":
    run()
