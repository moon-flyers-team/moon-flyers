"""Exercise deployment promotion and rollback without Docker or a live host."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class DeploymentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name).resolve()
        self.root = self.home / "moon-flyers" / "test"
        self.bin = self.home / "bin"
        self.bin.mkdir()
        self.log = self.home / "commands.log"
        self.environment = {
            **os.environ,
            "HOME": str(self.home),
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "COMMAND_LOG": str(self.log),
        }
        self.mock("docker", """#!/usr/bin/env bash
set -eu
printf 'docker %s\\n' "$*" >> "$COMMAND_LOG"
if [[ "$1" == compose && " $* " == *' up '* && -n ${FAIL_RELEASE:-} && "$*" == *"$FAIL_RELEASE"* ]]; then
  exit 1
fi
""")
        self.mock("python3", """#!/usr/bin/env bash
set -eu
printf 'smoke %s\\n' "$*" >> "$COMMAND_LOG"
[[ ${FAIL_SMOKE:-0} != 1 ]]
""")

    def mock(self, name: str, contents: str) -> None:
        executable = self.bin / name
        executable.write_text(contents)
        executable.chmod(0o755)

    def release(self, name: str, revision: str = "a" * 40, with_terrain_overlay: bool = True) -> Path:
        directory = self.root / "releases" / name
        directory.mkdir(parents=True)
        shutil.copyfile(Path(__file__).with_name("deploy.sh"), directory / "deploy.sh")
        (directory / "compose.yaml").write_text("services: {}\n")
        if with_terrain_overlay:
            shutil.copyfile(Path(__file__).with_name("compose.terrain.yaml"), directory / "compose.terrain.yaml")
        (directory / "images.tar").touch()
        (directory / "smoke-test.py").touch()
        (directory / "REVISION").write_text(revision + "\n")
        return directory

    def terrain_dataset(self, name: str = "dem") -> Path:
        directory = self.home / "moon-flyers" / "data" / "lola" / "v1" / name
        directory.mkdir(parents=True)
        (directory / "calibration.json").write_text("{}\n")
        return directory

    def enable_terrain(self, directory: Path | str) -> None:
        (self.root / "terrain-directory").write_text(f"{directory}\n")

    def run_release(self, directory: Path, target: str = "test", **overrides: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(directory / "deploy.sh"), target],
            env={**self.environment, **overrides},
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_first_success_promotes_only_after_health_check(self) -> None:
        release = self.release("first")
        result = self.run_release(release)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / "current").resolve(), release)
        self.assertFalse((self.root / "previous").is_symlink())
        self.assertEqual((release / ".env").read_text(), f"REVISION={'a' * 40}\nHTTP_PORT=18081\n")
        commands = self.log.read_text()
        self.assertIn("--project-name moon-flyers-test", commands)
        self.assertIn("--no-build --pull never --wait", commands)
        self.assertIn("http://127.0.0.1:18081", commands)
        self.assertNotIn(" down", commands)

    def test_production_has_separate_project_and_port(self) -> None:
        candidate = self.release("first")
        production = self.home / "moon-flyers" / "production"
        destination = production / "releases" / "first"
        destination.parent.mkdir(parents=True)
        shutil.move(str(candidate), destination)
        result = self.run_release(destination, "production")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((production / "current").resolve(), destination)
        self.assertIn("HTTP_PORT=18080", (destination / ".env").read_text())
        self.assertIn("--project-name moon-flyers-production", self.log.read_text())
        self.assertFalse((self.root / "current").exists())

    def test_second_success_retains_previous_release(self) -> None:
        first = self.release("first")
        second = self.release("second", "b" * 40)
        self.assertEqual(self.run_release(first).returncode, 0)
        self.assertEqual(self.run_release(second).returncode, 0)
        self.assertEqual((self.root / "current").resolve(), second)
        self.assertEqual((self.root / "previous").resolve(), first)

    def test_container_failure_restores_current_release(self) -> None:
        first = self.release("first")
        broken = self.release("broken", "b" * 40)
        self.assertEqual(self.run_release(first).returncode, 0)
        self.log.write_text("")
        result = self.run_release(broken, FAIL_RELEASE=str(broken))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual((self.root / "current").resolve(), first)
        commands = self.log.read_text().splitlines()
        starts = [line for line in commands if " up " in line]
        self.assertEqual(len(starts), 2)
        self.assertIn(str(broken), starts[0])
        self.assertIn(str(first), starts[1])
        self.assertFalse(any(" down" in line for line in commands))

    def test_first_failed_release_stops_stack_without_promotion(self) -> None:
        broken = self.release("broken")
        result = self.run_release(broken, FAIL_SMOKE="1")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertFalse((self.root / "current").is_symlink())
        self.assertIn(" down", self.log.read_text())

    def test_http_failure_also_rolls_back(self) -> None:
        first = self.release("first")
        broken = self.release("broken", "b" * 40)
        self.assertEqual(self.run_release(first).returncode, 0)
        result = self.run_release(broken, FAIL_SMOKE="1")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual((self.root / "current").resolve(), first)
        self.assertIn("restoring", result.stderr)

    def test_invalid_environment_is_rejected_before_docker(self) -> None:
        result = self.run_release(self.release("first"), "unknown")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.log.exists())

    def test_invalid_revision_is_rejected_before_docker(self) -> None:
        result = self.run_release(self.release("first", "not-a-commit"))
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.log.exists())

    def test_cross_environment_release_path_is_rejected(self) -> None:
        result = self.run_release(self.release("first"), "production")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.log.exists())

    def test_terrain_is_opt_in_and_absent_by_default(self) -> None:
        release = self.release("first")
        self.terrain_dataset()
        self.assertEqual(self.run_release(release).returncode, 0)
        self.assertNotIn("LOLA_DATA_DIR", (release / ".env").read_text())
        self.assertNotIn("compose.terrain.yaml", self.log.read_text())

    def test_terrain_directory_is_snapshotted_and_overlay_applied(self) -> None:
        dataset = self.terrain_dataset()
        release = self.release("first")
        self.enable_terrain(dataset)
        result = self.run_release(release)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((release / ".env").read_text(),
                         f"REVISION={'a' * 40}\nHTTP_PORT=18081\nLOLA_DATA_DIR={dataset}\n")
        commands = self.log.read_text()
        self.assertIn(f"-f {release}/compose.yaml -f {release}/compose.terrain.yaml up", commands)

    def test_terrain_rollback_does_not_inherit_new_host_configuration(self) -> None:
        first = self.release("first")
        second = self.release("second", "b" * 40)
        self.enable_terrain(self.terrain_dataset())
        self.assertEqual(self.run_release(first).returncode, 0)
        self.assertEqual(self.run_release(second).returncode, 0)
        # Disabling terrain must not be applied retroactively to the previous release.
        (self.root / "terrain-directory").unlink()
        self.log.write_text("")
        result = self.run_release(second, FAIL_SMOKE="1")
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"-f {second}/compose.yaml -f {second}/compose.terrain.yaml", self.log.read_text())
        self.assertIn(f"-f {first}/compose.yaml -f {first}/compose.terrain.yaml", self.log.read_text())

    def test_invalid_terrain_directory_is_rejected_before_docker(self) -> None:
        release = self.release("first")
        for value in ("relative/dem", "/does/not/exist", "/tmp/with space/dem"):
            self.enable_terrain(value)
            result = self.run_release(release)
            self.assertEqual(result.returncode, 2, value)
            self.assertIn("Invalid terrain-directory", result.stderr)
            self.assertFalse(self.log.exists(), value)

    def test_terrain_directory_requires_calibration_and_overlay(self) -> None:
        dataset = self.terrain_dataset()
        without_calibration = self.terrain_dataset("empty")
        (without_calibration / "calibration.json").unlink()
        for directory, release in ((without_calibration, self.release("first")),
                                   (dataset, self.release("second", with_terrain_overlay=False))):
            self.enable_terrain(directory)
            result = self.run_release(release)
            self.assertEqual(result.returncode, 2, str(directory))
            self.assertFalse(self.log.exists(), str(directory))


if __name__ == "__main__":
    unittest.main()
