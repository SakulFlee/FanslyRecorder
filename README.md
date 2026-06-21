# FanslyRecorder

Record Fansly live streams by intercepting m3u8 playlist URLs via Playwright and piping them through streamlink.

## Quick Start

### 1. Authenticate

Opens a browser window for you to log in to Fansly:

```sh
fansly-recorder --login
```

Saves the session to `fansly_auth.json` (Playwright storage state). All subsequent runs use this file headless.

### 2. Record a stream

```sh
fansly-recorder --url https://fansly.com/.../stream -o output.ts
```

The output filename defaults to `{streamer}_{timestamp}.ts`. Adding `-o output.ts` appends the timestamp before the extension (`output_20250101_120000.ts`).

## CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `--url` | — | Stream page URL to record |
| `-o` / `--output` | auto | Output file path template |
| `--login` | — | Interactive login to save auth state |
| `--storage-state` | `fansly_auth.json` | Path to saved auth state file |
| `--cdp-url` | `http://localhost:9222` | CDP URL for existing browser (fallback when no auth file exists) |
| `--monitor-time` | `15` | Seconds to wait for stream playlist on page load |

## Packages

### Nix

A `flake.nix` is provided for reproducible development and deployment.

#### Dev shell

```sh
nix develop
```

Provides Python 3.14, Playwright, streamlink, ffmpeg, and the Chromium browser with `PLAYWRIGHT_BROWSERS_PATH` preconfigured.

#### Run directly

```sh
nix run . -- --url https://fansly.com/.../stream -o output.ts
```

#### Build Docker image

```sh
nix build .#dockerImage
docker load < result
docker run fansly-recorder --help
```

### Binary Releases

Pre-built binaries are attached to [GitHub Releases](https://github.com/SakulFlee/FanslyRecorder/releases) and [Forgejo Releases](https://forgejo.sakul-flee.de/sakulflee/fansly-recorder/releases).

- **Linux**: `fansly-recorder-linux`
- **Windows**: `fansly-recorder-windows.exe`
- **macOS**: `fansly-recorder-macos`

> The binary is a PyInstaller bundle of the Python code only. On first run you need Playwright's Chromium browser installed:
>
> ```sh
> # Download Chromium to ~/.cache/ms-playwright/
> python -m playwright install chromium
> ```
>
> Set `PLAYWRIGHT_BROWSERS_PATH` to point elsewhere if needed.

### Docker

Images are published to:

- **GitHub**: `ghcr.io/sakulflee/fansly-recorder`
- **Forgejo**: `forgejo.sakul-flee.de/sakulflee/fansly-recorder`

Tags follow git tags (`v0.1.0`, etc.). The `latest` tag is updated on manual dispatches.

```sh
docker pull ghcr.io/sakulflee/fansly-recorder:latest
docker run --rm -v "$PWD:/data" ghcr.io/sakulflee/fansly-recorder \
  fansly-recorder --url https://fansly.com/.../stream -o /data/output.ts
```

## How It Works

1. **Authentication**: `--login` saves Playwright's browser storage state (cookies + localStorage) to a JSON file. Normal recording loads this state headless, avoiding repeated logins.

2. **m3u8 Capture**: A request handler on the Playwright page intercepts URLs containing `.m3u8`. The first detected playlist URL is used for recording.

3. **Recording**: The m3u8 URL is passed to `streamlink` as `hlsvariant://...`. Streamlink handles HLS segment downloading and reassembly.

4. **Stream Transitions**: The browser stays alive. If a new m3u8 URL appears (token refresh / stream restart), the old streamlink process is killed and a new one launched with the updated URL.

5. **Graceful Exit**: When streamlink exits and no new m3u8 is seen for 60 seconds, the script exits. Pressing Ctrl+C calls `os._exit(0)` (Playwright cleanup hangs on interrupt).

6. **CDP Fallback**: If no storage state file exists, the script connects to an existing Brave/Chrome instance via `--cdp-url` (default `http://localhost:9222`).

## CI/CD

| Pipeline | Trigger | Provider | Platforms |
|----------|---------|----------|-----------|
| Lint (`ruff check`) | push + PR | GitHub Actions + Woodpecker | Linux |
| Docker build + push | tags `v*` + manual | GitHub Actions (ghcr.io) + Woodpecker (Forgejo) | Linux |
| Binary release | tags `v*` | GitHub Actions | Linux, Windows, macOS |
| Binary release | tags `v*` | Woodpecker | Linux (Forgejo) |
