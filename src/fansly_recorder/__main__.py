import argparse
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime

from playwright.sync_api import Error, sync_playwright

DEFAULT_STORAGE = os.path.expanduser("~/.config/fansly-recorder/auth.json")
FANSLY_BROWSER_CHANNEL = os.environ.get("FANSLY_BROWSER_CHANNEL")


def login(args):
    print("Opening browser for Fansly login...", flush=True)
    print("Please log in to Fansly in the browser window that opens.", flush=True)
    print("After logging in, press Enter here to save the session.", flush=True)

    os.makedirs(os.path.dirname(args.storage_state) or ".", exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, channel=FANSLY_BROWSER_CHANNEL)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://fansly.com", wait_until="load")

        input("Press Enter after you have logged in...")

        context.storage_state(path=args.storage_state)
        print(f"Authentication state saved to {args.storage_state}", flush=True)

        page.close()
        browser.close()


def make_final_path(template, streamer, fmt="ts"):
    ts = datetime.now(UTC).strftime('%Y%m%d_%H%M%S')
    if template:
        base, _ = os.path.splitext(template)
        return f"{base}_{ts}.{fmt}"
    return f"{streamer}_{ts}.{fmt}"


def make_part_path(final_path, part_num):
    base, _ = os.path.splitext(final_path)
    return f"{base}_part{part_num:04d}.ts"


def concat_parts(part_files, final_path):
    if not part_files:
        return

    if len(part_files) == 1:
        os.rename(part_files[0], final_path)
        return

    parts_dir = os.path.dirname(os.path.abspath(final_path))
    fmt = final_path.rsplit('.', 1)[-1]

    if fmt == "ts":
        with open(final_path, 'wb') as out:
            for pf in part_files:
                with open(pf, 'rb') as f:
                    shutil.copyfileobj(f, out)
    else:
        filelist = os.path.join(parts_dir, '.filelist.txt')
        try:
            with open(filelist, 'w') as fl:
                for pf in part_files:
                    fl.write(f"file '{os.path.abspath(pf)}'\n")
            subprocess.run(
                ["ffmpeg", "-f", "concat", "-safe", "0",
                 "-i", filelist, "-c", "copy", os.path.abspath(final_path)],
                check=True, capture_output=True
            )
        finally:
            if os.path.exists(filelist):
                os.remove(filelist)

    for pf in part_files:
        os.remove(pf)


def build_streamlink_cmd(m3u8_url, cookie_string, output):
    return [
        "streamlink",
        f"hlsvariant://{m3u8_url}",
        "best",
        "--retry-open", "30",
        "-o", output,
        "--http-header", f"Cookie={cookie_string}",
        "--http-header", "User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ]


def get_cookie_string(context):
    cookies = context.cookies()
    return "; ".join([f"{c['name']}={c['value']}" for c in cookies])


def record_loop(args):
    storage_path = args.storage_state

    if not os.path.exists(storage_path) and sys.stdin.isatty():
        print(f"No saved authentication state found at {storage_path}.")
        print(f"  [L] Login now (saves to {storage_path})")
        print(f"  [C] Connect via CDP ({args.cdp_url})")
        print("  [Q] Quit")
        choice = input("Choose [L/c/q]: ").strip().lower()
        if choice in ("", "l"):
            login(args)
        elif choice == "c":
            pass
        else:
            sys.exit(0)

    with sync_playwright() as p:
        if os.path.exists(storage_path):
            print(f"Using saved authentication state from {storage_path}", flush=True)
            browser = p.chromium.launch(headless=True, channel=FANSLY_BROWSER_CHANNEL)
            context = browser.new_context(storage_state=storage_path)
            owns_browser = True
        else:
            print(f"No saved authentication state found at {storage_path}", flush=True)
            print(f"Connecting to your running browser on {args.cdp_url}...", flush=True)
            browser = p.chromium.connect_over_cdp(args.cdp_url)
            context = browser.contexts[0]
            owns_browser = False

        streamer = args.url.rstrip('/').split('/')[-1]
        page = context.new_page()
        current_m3u8 = None
        latest_m3u8 = None
        last_m3u8_time = 0.0

        def handle_request(request):
            nonlocal latest_m3u8, last_m3u8_time
            if ".m3u8" in request.url and "analytics" not in request.url:
                print(f"[FOUND STREAM] {request.url}", flush=True)
                latest_m3u8 = request.url
                last_m3u8_time = time.time()

        page.on("request", handle_request)

        print(f"Navigating to {args.url}...", flush=True)
        try:
            page.goto(args.url, wait_until="load", timeout=60000)
        except Error as e:
            print(f"[WARNING] Page load timed out: {e}", file=sys.stderr, flush=True)

        while True:
            latest_m3u8 = None
            last_m3u8_time = 0.0

            print(f"Waiting for stream playlist (up to {args.monitor_time}s)...", flush=True)
            for _ in range(args.monitor_time):
                if latest_m3u8:
                    break
                page.wait_for_timeout(1000)

            if not latest_m3u8:
                if not args.watch:
                    print("\n[ERROR] No m3u8 URL captured within timeout.", file=sys.stderr, flush=True)
                    break
                print(f"\nNo stream detected. Checking again in {args.interval}s...", flush=True)
                try:
                    time.sleep(args.interval)
                except KeyboardInterrupt:
                    print("\nWatch mode stopped by user.", flush=True)
                    break
                continue

            current_m3u8 = latest_m3u8
            last_m3u8_time = time.time()

            final_output = make_final_path(args.output, streamer, args.format)
            part_files = []
            part_counter = 0
            user_stopped = False

            while True:
                cookie_string = get_cookie_string(context)
                part_counter += 1
                part_path = make_part_path(final_output, part_counter)
                part_files.append(part_path)

                print(f"\nStarting stream recording to {part_path}...", flush=True)
                print("Press Ctrl+C to stop.", flush=True)

                proc = subprocess.Popen(
                    build_streamlink_cmd(current_m3u8, cookie_string, part_path),
                    start_new_session=True,
                )

                try:
                    restart = False

                    while proc.poll() is None:
                        if latest_m3u8 and latest_m3u8 != current_m3u8:
                            print("\n[NEXT] Stream URL refreshed, re-launching...", flush=True)
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

                    print(f"\n[STREAMLINK] Exited with code {proc.returncode}", flush=True)

                    m3u8_stale_timeout = 30
                    secs_since_m3u8 = time.time() - last_m3u8_time
                    if secs_since_m3u8 <= m3u8_stale_timeout:
                        print(f"[RETRY] Stream still active (last m3u8 {secs_since_m3u8:.0f}s ago), "
                              f"restarting in 2s...", flush=True)
                        if latest_m3u8 and latest_m3u8 != current_m3u8:
                            current_m3u8 = latest_m3u8
                        page.wait_for_timeout(2000)
                        continue

                    print(f"[RENAV] No m3u8 requests for {secs_since_m3u8:.0f}s, "
                          f"reloading page to get fresh token...", flush=True)
                    latest_m3u8 = None
                    try:
                        page.goto(args.url, wait_until="load", timeout=30000)
                    except Error as e:
                        print(f"[WARNING] Page reload timed out: {e}", file=sys.stderr, flush=True)

                    print(f"[RENAV] Page navigated, waiting up to {args.monitor_time}s for new playlist...", flush=True)
                    for _ in range(args.monitor_time):
                        if latest_m3u8:
                            break
                        page.wait_for_timeout(1000)

                    if latest_m3u8:
                        print(f"[RENAV] New playlist captured: {latest_m3u8}", flush=True)
                        current_m3u8 = latest_m3u8
                        last_m3u8_time = time.time()
                        page.wait_for_timeout(2000)
                        continue

                    print("\n[WAITING] No playlist found after reload, "
                          "waiting up to 60s for next stream...", flush=True)
                    for _ in range(120):
                        if time.time() - last_m3u8_time <= m3u8_stale_timeout:
                            print("\n[NEXT] Stream activity detected, restarting...", flush=True)
                            if latest_m3u8 and latest_m3u8 != current_m3u8:
                                current_m3u8 = latest_m3u8
                            break
                        page.wait_for_timeout(500)
                    else:
                        print("\nNo stream activity detected for 60s, exiting.", flush=True)
                        break

                except KeyboardInterrupt:
                    print("\nRecording stopped by user.", flush=True)
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    user_stopped = True
                    break

            if not args.no_concat and part_files:
                part_count = len(part_files)
                print(f"\nConcatenating {part_count} part{'s' if part_count > 1 else ''} into {final_output}...", flush=True)
                try:
                    concat_parts(part_files, final_output)
                    print(f"Done: {final_output}", flush=True)
                except subprocess.CalledProcessError as e:
                    print(f"[ERROR] Concatenation failed: {e}", file=sys.stderr, flush=True)
                    if e.stderr:
                        print(e.stderr.decode(errors="replace"), file=sys.stderr, flush=True)
                except OSError as e:
                    print(f"[ERROR] Concatenation failed: {e}", file=sys.stderr, flush=True)

            if user_stopped:
                break
            if not args.watch:
                break

            print(f"\nStream ended. Checking again in {args.interval}s...", flush=True)
            try:
                time.sleep(args.interval)
            except KeyboardInterrupt:
                print("\nWatch mode stopped by user.", flush=True)
                break

        page.close()
        if owns_browser:
            context.close()
            browser.close()


def run():
    parser = argparse.ArgumentParser(description="Fansly stream recorder")
    parser.add_argument("--url", help="Stream URL to record")
    parser.add_argument("-o", "--output", help="Output file path template")
    parser.add_argument("--format", default="ts",
                        help="Output container format (ts, mkv, mp4, etc.) (default: ts)")
    parser.add_argument("--no-concat", action="store_true",
                        help="Skip concatenation, keep .ts part files")
    parser.add_argument("--login", action="store_true",
                        help="Interactive login to save authentication state")
    parser.add_argument("--storage-state", default=DEFAULT_STORAGE,
                        help=f"Path to saved auth state file (default: {DEFAULT_STORAGE})")
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222",
                        help="CDP URL for existing browser (default: http://127.0.0.1:9222)")
    parser.add_argument("--monitor-time", type=int, default=15,
                        help="Seconds to wait for stream playlist (default: 15)")
    parser.add_argument("--watch", action="store_true",
                        help="Stay running, check for stream every N seconds")
    parser.add_argument("--interval", type=int, default=300,
                        help="Check interval in seconds (default: 300)")
    args = parser.parse_args()

    if args.format != "ts" and args.no_concat:
        print(f"Error: --no-concat cannot be used with --format {args.format} "
              f"(concatenation is required for non-TS output)", file=sys.stderr, flush=True)
        sys.exit(1)

    if args.login:
        login(args)
        return

    if not args.url:
        print("Error: --url is required for recording mode", file=sys.stderr, flush=True)
        sys.exit(1)

    record_loop(args)


if __name__ == "__main__":
    run()
