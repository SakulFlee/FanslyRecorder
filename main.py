import subprocess
import time
import sys
from playwright.sync_api import sync_playwright

# ==================== CONFIGURATION ====================
TARGET_URL = "https://fansly.com/live/test"  # Replace with your URL
OUTPUT_FILE = "live_recording.ts"                             # Name of the output file
CDP_URL = "http://localhost:9222"                             # Brave debugging port
MONITOR_TIME = 15                                             # Time (seconds) to wait for the stream link
# ========================================================

def run():
    with sync_playwright() as p:
        print(f"Connecting to your running Brave instance on {CDP_URL}...")
        
        try:
            # Connect directly to your open browser
            browser = p.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            print(f"\n[ERROR] Could not connect to Brave. Is it running with --remote-debugging-port=9222?")
            print(f"Details: {e}")
            sys.exit(1)
        
        # Access your open profile/session context
        context = browser.contexts[0]
        
        # Open a fresh tab in your existing window
        page = context.new_page()

        captured_urls = []

        # Network interceptor looking for the stream playlist
        def handle_request(request):
            url = request.url
            if ".m3u8" in url and "analytics" not in url:
                print(f"[FOUND STREAM] {url}")
                captured_urls.append(url)

        page.on("request", handle_request)

        print(f"Navigating to {TARGET_URL}...")
        try:
            page.goto(TARGET_URL, wait_until="load", timeout=60000)
        except Exception as e:
            print(f"[WARNING] Page load took a long time or timed out: {e}")

        print(f"Monitoring background network traffic for {MONITOR_TIME} seconds...")
        time.sleep(MONITOR_TIME)

        if not captured_urls:
            print("\n[ERROR] No m3u8 URL captured.")
            print("Check your Brave window—did the stream fail to auto-play, or did a popup block it?")
            page.close()
            return

        # Pick the latest captured URL (helps skip initial ad playlists)
        final_m3u8 = captured_urls[-1]
        
        # Scrape all live cookies associated with your authenticated profile session
        cookies = context.cookies()
        cookie_string = "; ".join([f"{c['name']}={c['value']}" for c in cookies])

        # Safely close only the tab created by this script
        page.close()

    # Pass the authenticated stream over to Streamlink
    print(f"\nHanding stream link and active login session over to Streamlink...")
    print(f"Recording to file: {OUTPUT_FILE}")
    print("Press Ctrl+C inside this terminal window to stop recording.")
    
    streamlink_cmd = [
        "streamlink",
        f"hlsvariant://{final_m3u8}",
        "best",
        "-o", OUTPUT_FILE,
        "--http-header", f"Cookie={cookie_string}",
        "--http-header", "User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ]
    
    try:
        subprocess.run(streamlink_cmd)
    except KeyboardInterrupt:
        print("\nRecording stopped by user. File saved.")

if __name__ == "__main__":
    run()
