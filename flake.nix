{
  description = "Fansly stream recorder";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};

      # Only Chromium + headless shell (~450 MB) instead of all browsers (~1.1 GB)
      playwrightBrowsers = pkgs.playwright-driver.selectBrowsers {
        withChromium = true;
        withChromiumHeadlessShell = true;
        withFfmpeg = false;
        withFirefox = false;
        withWebkit = false;
      };

      app = pkgs.writeShellApplication {
        name = "fansly-recorder";
        runtimeInputs = with pkgs; [
          python314
          python314Packages.playwright
          playwrightBrowsers
          streamlink
          ffmpeg
        ];
        text = ''
          export PLAYWRIGHT_BROWSERS_PATH="${playwrightBrowsers}"
          exec "${pkgs.python314}/bin/python" "${./main.py}" "$@"
        '';
      };
    in
    {
      devShells.${system}.default = pkgs.mkShell {
        buildInputs = with pkgs; [
          git
          ffmpeg
          python314
          python314Packages.playwright
          playwrightBrowsers
        ];

        shellHook = ''
          export PATH="${pkgs.streamlink}/bin:$PATH"
          export PLAYWRIGHT_BROWSERS_PATH="${playwrightBrowsers}"
        '';
      };

      packages.${system} = {
        default = app;

        dockerImage = pkgs.dockerTools.buildLayeredImage {
          name = "fansly-recorder";
          tag = "latest";
          contents = [ app ];
          config.Entrypoint = [ "fansly-recorder" ];
        };
      };
    };
}
