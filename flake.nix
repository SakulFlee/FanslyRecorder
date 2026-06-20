{
  description = "Python development environment";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};

      # Python environment with all required packages
      pyEnv = pkgs.python314.withPackages (ps: with ps; [
        playwright
        greenlet
      ]);
    in
    {
      devShells.${system}.default = pkgs.mkShell {
        buildInputs = [
          # Dev tools
          pkgs.git
          
          # Required tools to run
          pkgs.ffmpeg
          pkgs.streamlink

          # Python and dependencies (playwright, greenlet)
          pyEnv
        ];
      };
    };
}
