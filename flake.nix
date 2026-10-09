{
  description = "FRC 447 Slack daily report";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = {self, nixpkgs}: let
    systems = ["x86_64-linux" "aarch64-linux"];
    forAllSystems = f:
      nixpkgs.lib.genAttrs systems (system:
        f {pkgs = nixpkgs.legacyPackages.${system};});
    pythonEnv = pkgs:
      pkgs.python3.withPackages (ps: [
        ps.slack-sdk
        ps.psycopg
      ]);
  in {
    packages = forAllSystems ({pkgs}: {
      default = pkgs.stdenv.mkDerivation {
        pname = "slack-assistant";
        version = "0.1.0";
        src = ./src;
        nativeBuildInputs = [pkgs.makeWrapper];
        dontBuild = true;
        installPhase = ''
          mkdir -p $out/lib/slack-assistant
          cp -r slack_assistant $out/lib/slack-assistant/
          makeWrapper ${pythonEnv pkgs}/bin/python $out/bin/slack-assistant \
            --add-flags "-m slack_assistant" \
            --set PYTHONPATH $out/lib/slack-assistant
        '';
        meta.mainProgram = "slack-assistant";
      };
    });

    devShells = forAllSystems ({pkgs}: {
      default = pkgs.mkShell {
        packages = [
          (pkgs.python3.withPackages (ps: [
            ps.slack-sdk
            ps.psycopg
          ]))
        ];
        shellHook = ''
          export PYTHONPATH="$PWD/src''${PYTHONPATH:+:}$PYTHONPATH"
          export TZ="''${TZ:-America/Indiana/Indianapolis}"
        '';
      };
    });

    nixosModules.default = {pkgs, lib, ...}: {
      imports = [./nix/timer.nix];
      services.slack-assistant.package = lib.mkDefault self.packages.${pkgs.stdenv.hostPlatform.system}.default;
    };
  };
}
