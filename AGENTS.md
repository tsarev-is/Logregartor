# Repository Guidelines

## Project Structure & Module Organization

Logregartor is an early-stage hackathon project for OpenStack log analysis, anomaly detection, and evidence-based failure explanations.

- `src/LogParser/` contains the Go module (`logparser`); `main.go` currently prints a greeting.
- `docker-compose.yml` defines the local ClickHouse service and persistent `clickhouse_data` volume.
- `README.md` describes the proposed architecture and local database setup.
- `docs/AI_Powered_Observability_Hackathon_1.pdf` contains the project brief.

Vector search, AI analytics, and a dashboard are planned components. No tests or application assets are committed yet.

## Build, Test, and Development Commands

Use a Go toolchain compatible with `src/LogParser/go.mod` (currently `go 1.26.3`) and Docker Compose.

Run from the repository root:

```bash
docker compose up -d --wait clickhouse  # Start ClickHouse and await health.
docker compose config --quiet          # Validate Compose configuration.
docker compose down                    # Stop services; retain database volume.
```

Run Go commands from `src/LogParser/`:

```bash
go run .          # Run the current entry point.
go build ./...    # Compile all packages.
go test ./...     # Run all package tests once added.
go vet ./...      # Check for common Go mistakes.
gofmt -w .        # Format Go source files.
```

## Coding Style & Naming Conventions

Use standard Go formatting via `gofmt`, including tab indentation. Use lowercase package names, `MixedCaps` identifiers, and capitalized names only for exported symbols. Keep package responsibilities focused and pass service configuration explicitly. Use two-space indentation in Compose YAML. No additional formatter or linter configuration is committed.

## Testing Guidelines

Use Go's standard `testing` package. Place tests beside their implementation in `*_test.go` files and name functions `TestXxx`. For parser work, cover valid log records, malformed input, and empty input. Document any ClickHouse dependency and setup steps for integration tests. No coverage threshold is configured.

## Commit & Pull Request Guidelines

History currently contains only `Init task` and `Init commit`; no formal commit convention is established. Use concise, imperative subjects describing a focused change. Pull requests should explain the behavior changed, list validation commands and results, and link relevant issues. Include screenshots for future dashboard changes.

## Security & Configuration Tips

Override database settings through the `CLICKHOUSE_*` variables in Compose. Keep secrets in ignored local `.env` files. The default `localdev` password is for local development. Avoid `docker compose down -v` unless intentionally deleting stored logs.
