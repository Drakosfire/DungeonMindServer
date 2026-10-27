"""Provider-free static checks for the proposed DMS uv/systemd deployment files."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / "deploy/production/systemd/dungeonmind-server.service"
ENV_EXAMPLE = ROOT / "deploy/production/systemd/dms.env.example"
RUNBOOK = ROOT / "Docs/Runbooks/RUNBOOK-HOSTED-uv-systemd-preparation.md"


class UvSystemdDeploymentContractTests(unittest.TestCase):
    def test_unit_executes_prepared_release_directly_on_loopback(self):
        unit = UNIT.read_text()
        self.assertIn("WorkingDirectory=/opt/dungeonmindserver/current", unit)
        self.assertIn("EnvironmentFile=/etc/dungeonmindserver/dms.env", unit)
        self.assertIn(
            "ExecStart=/opt/dungeonmindserver/current/.venv/bin/uvicorn app:app --host 127.0.0.1 --port 7860",
            unit,
        )
        self.assertIn("ProtectSystem=strict", unit)
        self.assertIn("ProtectHome=true", unit)
        self.assertIn("ReadWritePaths=/var/lib/dungeonmindserver /var/cache/dungeonmindserver", unit)
        for forbidden in ("uv sync", "uv run", "alembic", "migrate", "docker", "0.0.0.0"):
            self.assertNotIn(forbidden, unit.lower())

    def test_environment_template_blocks_implicit_local_mongo_fallback(self):
        env = ENV_EXAMPLE.read_text()
        values = {
            line.partition("=")[0]: line.partition("=")[2]
            for line in env.splitlines()
            if line and not line.startswith("#") and "=" in line
        }
        self.assertEqual(values["ENVIRONMENT"], "production")
        self.assertEqual(values["MONGODB_URI"], "REPLACE_WITH_DEDICATED_MONGODB_URI")
        self.assertEqual(values["SERVICE_ACCOUNT_PATH"], "/etc/dungeonmindserver/secrets/service-account.json")
        self.assertEqual(values["RULESLAWYER_DATA_DIR"], "/var/lib/dungeonmindserver/ruleslawyer-data")
        self.assertEqual(values["OPENAI_API_KEY"], "REPLACE_WITH_SECRET")
        self.assertEqual(values["TWILIO_TEST_MODE"], "false")
        self.assertTrue(all(value.startswith("REPLACE_") or value.startswith("/") or value in {"production", "false"}
                            for value in values.values()))

    def test_release_instructions_preserve_lock_and_single_proxy(self):
        runbook = RUNBOOK.read_text()
        self.assertIn("uv sync --locked --python 3.11 --no-dev --no-editable", runbook)
        self.assertIn("does not invoke uv", runbook)
        self.assertIn("already-running Nginx", runbook)
        self.assertIn("Do not create another Nginx", runbook)
        self.assertIn("Python 3.13", runbook)
        self.assertTrue((ROOT / "uv.lock").is_file())


if __name__ == "__main__":
    unittest.main()
