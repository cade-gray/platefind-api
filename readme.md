# platefind-api

A Go REST API that serves the US license plate catalog behind **PlateFind** — each
plate's state, design name, description, the reasoning behind the design, and the
SVG artwork for it. Built with Gin and GORM, backed by PostgreSQL, containerized
for deployment to a VPS.

## Features

- REST endpoints for the license plate catalog
- PostgreSQL integration via GORM
- Per-plate SVG artwork stored alongside the design metadata
- Dockerized for local and remote deployment
- Environment-based configuration
- CI/CD to GitHub Container Registry and a DigitalOcean VPS

## Endpoints

| Method | Path          | Description                     |
| ------ | ------------- | ------------------------------- |
| `GET`  | `/plates`     | List all plates                 |
| `GET`  | `/plates/:id` | Get a single plate by ID        |
| `GET`  | `/health`     | Liveness check (`{"status":"ok"}`) |

### Plate shape

```json
{
  "id": 1,
  "state": "Alabama",
  "country": "United States",
  "design_name": "Standard White Plate",
  "design_description": "White background with county code, 'Sweet Home Alabama' text at bottom",
  "design_reasoning": "References the iconic Lynyrd Skynyrd song to promote state tourism...",
  "svg_code": "<svg viewBox=\"0 0 300 150\">...</svg>"
}
```

`svg_code` is `null` for any plate whose design has not been drawn yet.

## Getting Started

### Prerequisites

- Go 1.21+
- Docker & Docker Compose
- PostgreSQL

### Local Development

1. Clone and enter the repo:

   ```sh
   git clone https://github.com/USERNAME/platefind-api.git
   cd platefind-api
   ```

2. Set your database credentials in `compose.yaml` (or a local
   `compose.dev.yaml`, which is gitignored):

   ```yaml
   environment:
     - DB_HOST=localhost
     - DB_USER=youruser
     - DB_PASSWORD=yourpass
     - DB_NAME=platefind_db
     - DB_PORT=5432
     - DB_SSLMODE=disable
   ```

3. Build and run:

   ```sh
   docker compose up --build
   ```

4. The API is at [http://localhost:4269](http://localhost:4269).

Running without Docker works too — export the same `DB_*` variables and
`go run .`.

## Database

### Schema

`CREATE_SQLS.sql` holds the full schema (database, tables, `updated_at`
triggers, and the `gorm` role). Seed data for the plates table lives in
`us-license-plates-imp.csv`.

```sql
CREATE DATABASE platefind_db;
CREATE USER gorm WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE platefind_db TO gorm;
```

Import the seed CSV:

```sh
psql -U gorm -d platefind_db -c "\copy plates(state,country,design_name,design_description,design_reasoning) FROM 'us-license-plates-imp.csv' WITH (FORMAT csv, HEADER true)"
```

### Migrations

Incremental changes live in `migrations/`, applied in filename order:

```sh
psql -U gorm -d platefind_db -f migrations/001_add_svg_code_to_plates.sql
```

- `001_add_svg_code_to_plates.sql` — adds the nullable `svg_code TEXT` column
  that stores each plate's SVG markup.
- `002_plate_svgs.sql` — fills `svg_code` for all 51 plates. Generated; see
  Plate artwork below.

## Plate artwork

`scripts/build_plate_svgs.py` is the source of truth for every plate design.
Running it writes three things and nothing else:

```sh
python3 scripts/build_plate_svgs.py
```

| Output | What it is |
| --- | --- |
| `plate-svgs/<state>.svg` | one file per plate, for eyeballing a single design |
| `plate-svgs/preview.html` | all 51 on one page |
| `migrations/002_plate_svgs.sql` | the `UPDATE` statements that load them |

Edit the generator, never the SQL or the SVG files — they are overwritten on
every run. The script fails if the set of designs drifts from the states in
`us-license-plates-imp.csv`.

Load the artwork (safe to re-run; it only overwrites `svg_code`):

```sh
psql -U gorm -d platefind_db -f migrations/002_plate_svgs.sql
```

It matches on `state` and finishes by listing any plate still missing artwork —
an empty result means all 51 landed.

Each design is a 300x150 viewBox, the true 2:1 proportion of a 12x6in plate,
with `width`/`height` at 100% so it fills whatever box the UI gives it. There
are no external references, so the markup can be inlined directly. Gradient and
clip `id`s are prefixed with the state slug because the board renders all 51
into one document, and duplicate ids would cross-wire the fills.

## Deployment

### Automated (GitHub Actions)

`.github/workflows/deploy.yml` builds a multi-platform image (amd64 + arm64),
pushes it to GitHub Container Registry, and deploys it over SSH on every push to
`main`. Pull requests build to prove the image still compiles and stop there —
they never push, so they cannot move the `:latest` tag the VPS pulls.

The deploy step pulls the latest image, recreates the container from the compose
file on the VPS (`/srv/platefind-api/compose.dev.yaml`), and ensures the
container is set to restart automatically.

> **`compose.dev.yaml` has to name the published image.** It is gitignored and
> lives only on the VPS, so nothing in CI can check it. Its `server` service must
> read `image: ghcr.io/cade-gray/platefind-api:latest` — no `build:` block. If it
> names anything else, every deploy still reports success: the workflow pulls the
> new image, then compose recreates the container from whatever the file actually
> points at, and production silently keeps running old code.

#### Repository secrets

| Secret         | Value                                   |
| -------------- | --------------------------------------- |
| `GH_TOKEN`     | GitHub PAT with `write:packages`        |
| `VPS_HOST`     | VPS IP address or hostname              |
| `VPS_USER`     | SSH username (e.g. `root`)              |
| `VPS_SSH_KEY`  | Private SSH key authorized on the VPS   |

Set them with the `gh` CLI from inside the repo:

```sh
gh secret set GH_TOKEN                      # paste the token when prompted
gh secret set VPS_HOST    --body "1.2.3.4"
gh secret set VPS_USER    --body "root"
gh secret set VPS_SSH_KEY < ~/.ssh/id_ed25519
```

`gh secret set NAME` with no value prompts for it, which keeps the secret out of
your shell history. Verify with `gh secret list`.

The SSH key must be a private key whose public half is in the VPS's
`~/.ssh/authorized_keys`:

```sh
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/platefind_deploy
ssh-copy-id -i ~/.ssh/platefind_deploy.pub VPS_USER@VPS_HOST
gh secret set VPS_SSH_KEY < ~/.ssh/platefind_deploy
```

### Manual

```sh
docker build -t ghcr.io/USERNAME/platefind-api:latest .
docker push ghcr.io/USERNAME/platefind-api:latest
```

On the VPS:

```sh
cd /srv/platefind-api
docker compose -f compose.dev.yaml up -d
```

### Surviving a reboot

Two things have to be true for the API to come back after the host restarts:

1. **The container has a restart policy.** `compose.yaml` sets
   `restart: unless-stopped`; the compose file on the VPS needs the same line
   under its `server` service. To apply it to an already-running container
   without recreating it:

   ```sh
   docker update --restart unless-stopped <container>
   ```

2. **The Docker daemon starts on boot.** One-time host setup, done by hand —
   the deploy user cannot run `systemctl` as root, so CI cannot do this:

   ```sh
   sudo systemctl enable docker
   ```

Verify with `docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' <container>`.

## Project Structure

```text
main.go                 # Entry point, DB connection, route registration
routes/plates.go        # Plate model and /plates handlers
migrations/             # Incremental SQL migrations
scripts/build_plate_svgs.py # Draws every plate; emits the SVGs and 002_*.sql
plate-svgs/             # Generated artwork, one SVG per plate + preview.html
CREATE_SQLS.sql         # Full schema + role setup
us-license-plates-imp.csv  # Seed data
Dockerfile              # Multi-stage build
compose.yaml            # Local Compose config
.github/workflows/      # CI/CD pipeline
```
