{
  description = "Python development environment";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
    in
    {
      devShells.${system}.default = pkgs.mkShell {
        buildInputs = [
          pkgs.git
          pkgs.ffmpeg
          pkgs.python314
          pkgs.python314Packages.playwright
          pkgs.playwright-driver.browsers
        ];

        shellHook = ''
          export PATH="${pkgs.streamlink}/bin:$PATH"
          export PLAYWRIGHT_BROWSERS_PATH="${pkgs.playwright-driver.browsers}"
        '';
      };
    };
}
