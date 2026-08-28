{
  description = "Fansly stream recorder";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];

      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f system);

      pkgsFor = system: nixpkgs.legacyPackages.${system};

      mkApp = system:
        let
          pkgs = pkgsFor system;

          playwrightBrowsers = pkgs.playwright-driver.selectBrowsers {
            withChromium = true;
            withChromiumHeadlessShell = true;
            withFfmpeg = false;
            withFirefox = false;
            withWebkit = false;
          };
        in
        pkgs.python314.pkgs.buildPythonApplication {
          pname = "fansly-recorder";
          version = "0.1.30";
          src = ./.;
          format = "pyproject";
          nativeBuildInputs = with pkgs.python314Packages; [
            setuptools
            wheel
          ];
          propagatedBuildInputs = with pkgs.python314Packages; [
            playwright
          ];
          postInstall = ''
            wrapProgram "$out/bin/fansly-recorder" \
              --set PLAYWRIGHT_BROWSERS_PATH "${playwrightBrowsers}" \
              --prefix PATH : "${pkgs.streamlink}/bin:${pkgs.ffmpeg}/bin"
          '';
          doCheck = false;
        };

      mkDevShell = system:
        let
          pkgs = pkgsFor system;

          playwrightBrowsers = pkgs.playwright-driver.selectBrowsers {
            withChromium = true;
            withChromiumHeadlessShell = true;
            withFfmpeg = false;
            withFirefox = false;
            withWebkit = false;
          };
        in
        pkgs.mkShell {
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

      mkDockerImage = system:
        let
          pkgs = pkgsFor system;
        in
        pkgs.dockerTools.buildLayeredImage {
          name = "fansly-recorder";
          tag = "latest";
          contents = [
            self.packages.${system}.default
            pkgs.bash
            pkgs.coreutils
          ];
          config.Entrypoint = [ "fansly-recorder" ];
        };
    in
    {
      devShells = forAllSystems (system: {
        default = mkDevShell system;
      });

      packages = forAllSystems (system: {
        default = mkApp system;
        dockerImage = mkDockerImage system;
      });
    };
}
