from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import patch


def _run_ai(*args):
    script = Path(__file__).resolve().parents[1] / "ai"
    stdout = StringIO()
    with patch.object(sys, "argv", ["ai", *args]), redirect_stdout(stdout):
        try:
            runpy.run_path(str(script), run_name="__main__")
        except SystemExit as error:
            exit_code = error.code
        else:
            exit_code = 0
    return exit_code, stdout.getvalue()


class CliUsageTests(unittest.TestCase):
    def test_no_args_and_help_flags_print_local_ai_stack_usage_and_exit_zero(self):
        for args in ([], ["--help"], ["-h"], ["help"]):
            with self.subTest(args=args):
                exit_code, output = _run_ai(*args)
                self.assertEqual(0, exit_code)
                self.assertIn("Local AI Stack", output)
                self.assertNotIn("AI Platform", output)
                self.assertIn("Usage: ./ai <command>", output)
                self.assertIn("preflight", output)

    def test_unknown_command_prints_error_and_usage_and_exits_nonzero(self):
        exit_code, output = _run_ai("nonexistent-cmd")
        self.assertEqual(1, exit_code)
        self.assertIn("Unknown command: nonexistent-cmd", output)
        self.assertIn("Local AI Stack", output)
        self.assertIn("Usage: ./ai <command>", output)
