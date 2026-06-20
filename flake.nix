{
  description = "Fansly stream recorder";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};

      app = pkgs.writeShellApplication {
        name = "fansly-recorder";
        runtimeInputs = with pkgs; [
          python314
          python314Packages.playwright
          playwright-driver.browsers
          streamlink
          ffmpeg
        ];
        text = ''
          export PLAYWRIGHT_BROWSERS_PATH="${pkgs.playwright-driver.browsers}"
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
          playwright-driver.browsers
        ];

        shellHook = ''
          export PATH="${pkgs.streamlink}/bin:$PATH"
          export PLAYWRIGHT_BROWSERS_PATH="${pkgs.playwright-driver.browsers}"
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
