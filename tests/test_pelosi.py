import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

from _load import load

ptr = load("trader-pelosi", "ptr")


class UnsupportedDisclosureTracker(unittest.TestCase):
    def test_all_commands_refuse_us_congress_data(self):
        for args in (["index"], ["new", "--member", "pelosi"], ["fetch", "20035143"]):
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = ptr.main(args)
            self.assertEqual(code, 2)
            self.assertEqual(out.getvalue(), "")
            self.assertIn("unsupported for NSE-only research", err.getvalue())
            self.assertIn("No US disclosure data", err.getvalue())

    def test_old_us_options_are_not_available(self):
        err = io.StringIO()
        with redirect_stderr(err):
            code = ptr.main(["index", "--offline", "tests/fixtures/trader-pelosi/2026FD.zip"])
        self.assertEqual(code, 2)
        self.assertIn("No US disclosure data", err.getvalue())


if __name__ == "__main__":
    unittest.main()
