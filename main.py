import argparse
import os
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


def make_output_path(template, streamer):
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    if template:
        base, ext = os.path.splitext(template)
        return f"{base}_{ts}{ext}"
    return f"{streamer}_{ts}.ts"


def build_streamlink_cmd(m3u8_url, cookie_string, output):
    return [
        "streamlink",
        f"hlsvariant://{m3u8_url}",
        "best",
        "--retry-open", "10",
        "-o", output,
        "--http-header", f"Cookie={cookie_string}",
        "--http-header", "User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ]


def get_cookie_string(context):
    cookies = context.cookies()
    return "; ".join([f"{c['name']}={c['value']}" for c in cookies])


def record_loop(args):
    with sync_playwright() as p:
        if os.path.exists(args.storage_state):
            print(f"Using saved authentication state from {args.storage_state}", flush=True)
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(storage_state=args.storage_state)
            owns_browser = True
        else:
            print(f"No saved authentication state found at {args.storage_state}", flush=True)
            print(f"Connecting to your running Brave instance on {args.cdp_url}...", flush=True)
            browser = p.chromium.connect_over_cdp(args.cdp_url)
            context = browser.contexts[0]
            owns_browser = False

        streamer = args.url.rstrip('/').split('/')[-1]
        page = context.new_page()
        current_m3u8 = None
        latest_m3u8 = None

        def handle_request(request):
            nonlocal latest_m3u8
            if ".m3u8" in request.url and "analytics" not in request.url:
                print(f"[FOUND STREAM] {request.url}", flush=True)
                latest_m3u8 = request.url

        page.on("request", handle_request)

        print(f"Navigating to {args.url}...", flush=True)
        try:
            page.goto(args.url, wait_until="load", timeout=60000)
        except Exception as e:
            print(f"[WARNING] Page load timed out: {e}", file=sys.stderr, flush=True)

        print(f"Waiting for stream playlist (up to {args.monitor_time}s)...", flush=True)
        for _ in range(args.monitor_time):
            if latest_m3u8:
                break
            page.wait_for_timeout(1000)

        if not latest_m3u8:
            print("\n[ERROR] No m3u8 URL captured within timeout.", file=sys.stderr, flush=True)
            return

        current_m3u8 = latest_m3u8

        while True:
            cookie_string = get_cookie_string(context)
            output = make_output_path(args.output, streamer)

            print(f"\nStarting stream recording to {output}...", flush=True)
            print("Press Ctrl+C to stop.", flush=True)

            proc = subprocess.Popen(
                build_streamlink_cmd(current_m3u8, cookie_string, output),
                start_new_session=True,
            )

            try:
                restart = False

                while proc.poll() is None:
                    if latest_m3u8 and latest_m3u8 != current_m3u8:
                        print(f"\n[NEXT] Stream URL refreshed, re-launching...", flush=True)
                        proc.terminate()
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                        current_m3u8 = latest_m3u8
                        restart = True
                        break
                    page.wait_for_timeout(500)

                if restart:
                    continue

                if proc.returncode != 0:
                    print(f"\n[WARNING] Streamlink exited with code {proc.returncode}",
                          file=sys.stderr, flush=True)

                if latest_m3u8 and latest_m3u8 != current_m3u8:
                    print(f"\n[NEXT] New stream detected, starting next recording...", flush=True)
                    current_m3u8 = latest_m3u8
                    continue

                print(f"\n[WAITING] Stream ended, waiting up to 60s for next stream...", flush=True)
                for _ in range(120):
                    if latest_m3u8 and latest_m3u8 != current_m3u8:
                        print(f"\n[NEXT] New stream detected, starting next recording...", flush=True)
                        current_m3u8 = latest_m3u8
                        break
                    page.wait_for_timeout(500)
                else:
                    print("\nNo new stream detected for 60s, exiting.", flush=True)
                    break

            except KeyboardInterrupt:
                print("\nRecording stopped by user.", flush=True)
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                os._exit(0)

        page.close()
        if owns_browser:
            context.close()
            browser.close()


def run():
    parser = argparse.ArgumentParser(description="Fansly stream recorder")
    parser.add_argument("--url", help="Stream URL to record")
    parser.add_argument("-o", "--output", help="Output file path template")
    parser.add_argument("--login", action="store_true",
                        help="Interactive login to save authentication state")
    parser.add_argument("--storage-state", default="fansly_auth.json",
                        help="Path to saved auth state file (default: fansly_auth.json)")
    parser.add_argument("--cdp-url", default="http://localhost:9222",
                        help="CDP URL for existing browser (default: http://localhost:9222)")
    parser.add_argument("--monitor-time", type=int, default=15,
                        help="Seconds to wait for stream playlist (default: 15)")
    args = parser.parse_args()

    if args.login:
        login(args)
        return

    if not args.url:
        print("Error: --url is required for recording mode", file=sys.stderr, flush=True)
        sys.exit(1)

    record_loop(args)


if __name__ == "__main__":
    run()
