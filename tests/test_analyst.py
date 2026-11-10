import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

from _load import load

facts = load("trader-analyst", "facts")


class UnsupportedAnalyst(unittest.TestCase):
    def test_refuses_to_fetch_us_facts_for_indian_ticker(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = facts.main(["RELIANCE"])
        self.assertEqual(code, 2)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("unsupported for NSE-only research", err.getvalue())
        self.assertIn("will not query SEC/EDGAR", err.getvalue())

    def test_does_not_accept_old_us_data_options(self):
        err = io.StringIO()
        with redirect_stderr(err), self.assertRaises(SystemExit) as raised:
            facts.main(["RELIANCE", "--offline", "tests/fixtures/trader-analyst"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("unrecognized arguments", err.getvalue())

    def test_help_describes_unsupported_tool(self):
        out = io.StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit) as raised:
            facts.main(["--help"])
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("unsupported", out.getvalue())


if __name__ == "__main__":
    unittest.main()
