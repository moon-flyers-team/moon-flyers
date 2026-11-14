#!/usr/bin/env bash
# Run from an extracted, trusted release bundle on Beelink. No sudo required.
set -euo pipefail

case "${1:-}" in
  production) http_port=18080 ;;
  test) http_port=18081 ;;
  *) echo "Usage: bash deploy.sh production|test" >&2; exit 2 ;;
esac

environment=$1
release_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
root="$HOME/moon-flyers/$environment"
revision=$(<"$release_dir/REVISION")
if [[ ! $revision =~ ^[0-9a-f]{40}$ ]]; then
  echo "Invalid release revision" >&2
  exit 2
fi
if [[ $release_dir != "$root/releases/"* ]]; then
  echo "Release must be extracted under $root/releases/" >&2
  exit 2
fi

# Also protects against manual deployments racing a GitHub deployment.
exec 9>"$root/deploy.lock"
flock -w 300 9
previous=''
if [[ -L $root/current ]]; then
  previous=$(readlink -f "$root/current")
  if [[ ! -f $previous/compose.yaml || ! -f $previous/.env ]]; then
    echo "Current release is invalid; refusing to replace it" >&2
    exit 1
  fi
fi
printf 'REVISION=%s\nHTTP_PORT=%s\n' "$revision" "$http_port" > "$release_dir/.env"

# Opt-in per environment. Snapshot the absolute dataset path into this release so
# rollback does not pick up later host configuration changes. Never source shell.
if [[ -f $root/terrain-directory ]]; then
  terrain_directory=$(<"$root/terrain-directory")
  if [[ ! $terrain_directory =~ ^/[a-zA-Z0-9_./-]+$ \
        || ! -d $terrain_directory || ! -r $terrain_directory/calibration.json \
        || ! -f $release_dir/compose.terrain.yaml ]]; then
    echo "Invalid terrain-directory: need an absolute path without whitespace, a calibration.json, and terrain overlay" >&2
    exit 2
  fi
  printf 'LOLA_DATA_DIR=%s\n' "$terrain_directory" >> "$release_dir/.env"
fi

compose() {
  local directory=$1
  shift
  local overlays=()
  if grep -q '^LOLA_DATA_DIR=' "$directory/.env"; then
    overlays=(-f "$directory/compose.terrain.yaml")
  fi
  docker compose --project-name "moon-flyers-$environment" \
    --env-file "$directory/.env" -f "$directory/compose.yaml" "${overlays[@]}" "$@"
}

# Never pull mutable tags or build on the production host.
docker load --input "$release_dir/images.tar"
if compose "$release_dir" up --detach --no-build --pull never --wait --wait-timeout 120 \
  && python3 "$release_dir/smoke-test.py" "http://127.0.0.1:$http_port"; then
  if [[ -n $previous && $previous != "$release_dir" ]]; then
    ln -sfn "$previous" "$root/previous"
  fi
  ln -sfn "$release_dir" "$root/current"
  echo "Deployed $revision to $environment (127.0.0.1:$http_port)"
else
  compose "$release_dir" logs --no-color --tail 100 >&2 || true
  if [[ -n $previous && -f $previous/compose.yaml ]]; then
    echo "Deployment failed; restoring $previous" >&2
    compose "$previous" up --detach --no-build --pull never --wait --wait-timeout 120
  else
    echo "First deployment failed; stopping the failed stack" >&2
    compose "$release_dir" down
  fi
  exit 1
fi
