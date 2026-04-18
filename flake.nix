{
  description = "Bracket tournament system";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in
      {
        devShells.default = pkgs.mkShell {
          packages = [
            # Backend
            pkgs.uv
            pkgs.python314

            # Frontend + docs
            pkgs.nodejs_22
            pkgs.pnpm

            # Database
            pkgs.postgresql_17
            pkgs.process-compose
          ];

          shellHook = ''
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
          '';
        };
      });
}
