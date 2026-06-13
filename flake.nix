{
  description = "Bracket tournament system";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";

    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
    };

    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
    };
  };

  outputs = {
    self,
    nixpkgs,
    flake-utils,
    pyproject-nix,
    uv2nix,
    pyproject-build-systems,
  }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        lib = pkgs.lib;

        python = pkgs.python313;
        workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./backend; };

        pythonBase = pkgs.callPackage pyproject-nix.build.packages {
          inherit python;
        };

        pythonSet = pythonBase.overrideScope (
          lib.composeManyExtensions [
            pyproject-build-systems.overlays.wheel
            (workspace.mkPyprojectOverlay {
              sourcePreference = "wheel";
            })
          ]
        );

        backendEnv = pythonSet.mkVirtualEnv "bracket-backend-env" workspace.deps.all;

        # manylinux wheels installed by `uv` into `.venv` (numpy, ortools) link
        # libstdc++ / libz at runtime, which aren't on the loader path in a pure
        # nix shell. Expose them so `uv run` works for the CLI and process-compose.
        wheelLibraryPath = lib.makeLibraryPath [
          pkgs.stdenv.cc.cc.lib
          pkgs.zlib
        ];
      in
      {
        devShells.default = pkgs.mkShell {
          packages = [
            backendEnv
            pkgs.uv

            # Frontend + docs
            pkgs.nodejs_22
            pkgs.pnpm

            # Database
            pkgs.postgresql_17
            pkgs.process-compose
          ];

          env = {
            UV_NO_SYNC = "1";
            UV_PYTHON = python.interpreter;
            UV_PYTHON_DOWNLOADS = "never";
          };

          shellHook = ''
            unset PYTHONPATH

            export LD_LIBRARY_PATH="${wheelLibraryPath}''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

            export PGDATA="$PWD/.pgdata"
            export PGHOST="$PGDATA"  # use unix socket in PGDATA dir
            export PGPORT=5432
            export PG_DSN="postgresql://bracket_dev:bracket_dev@localhost:$PGPORT/bracket_dev"
            export CORS_ORIGINS="http://localhost:3000"
            export ENVIRONMENT="DEVELOPMENT"

            if [ ! -d "$PGDATA" ]; then
              echo "Initialising local Postgres cluster..."
              initdb --auth=trust --no-locale --encoding=UTF8 -D "$PGDATA" > /dev/null
              echo "unix_socket_directories = '$PGDATA'" >> "$PGDATA/postgresql.conf"
            fi

            if ! pg_ctl status -D "$PGDATA" > /dev/null 2>&1; then
              echo "Starting Postgres..."
              pg_ctl start -D "$PGDATA" -l "$PGDATA/postgresql.log" --wait
              psql -d postgres -c "CREATE USER bracket_dev WITH PASSWORD 'bracket_dev';" 2>/dev/null || true
              psql -d postgres -c "CREATE DATABASE bracket_dev OWNER bracket_dev;" 2>/dev/null || true
            fi

            trap "echo 'Stopping Postgres...'; pg_ctl stop -D '$PGDATA' --wait" EXIT

            alias dev="process-compose up -f process-compose-example.yml"
          '';
        };
      });
}
