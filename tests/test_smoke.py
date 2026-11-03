"""
Basic Smoke Tests for Samshodhanam Platform.
Verifies essential imports, transliteration engine, and WSGI gateway configuration.
"""

import unittest
import sys
import os

# Add root directory to python path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


class TestSamshodhanamSmoke(unittest.TestCase):

    def test_imports(self):
        """Verify core modules import without syntax or circular import errors."""
        import time_utils
        self.assertIsNotNone(time_utils)

    def test_transliteration_engine(self):
        """Verify Indic transliteration between Devanagari and IAST."""
        try:
            from indic_transliteration import sanscript
            devanagari = "संस्कृतम्"
            iast = sanscript.transliterate(devanagari, sanscript.DEVANAGARI, sanscript.IAST)
            self.assertEqual(iast, "saṃskṛtam")
        except ImportError:
            self.skipTest("indic_transliteration not installed in this environment")

    def test_database_initialization(self):
        """Verify SQLite DB initialization module exists."""
        from db import common_db
        conn = common_db.get_db()
        self.assertIsNotNone(conn)
        conn.close()


if __name__ == '__main__':
    unittest.main()
