"""
Unit tests for HistoricalMessageFetcher

Specifically tests that get_database_stats() uses key-based (column-name)
access on RealDictRow-style results rather than integer index access.
"""

import os
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

# Inject required env vars so config.py doesn't raise ValueError on import
_ENV_DEFAULTS = {
    "DATABASE_URL": "postgresql://fake:fake@localhost:5432/fakedb",
    "TELEGRAM_API_ID": "12345",
    "TELEGRAM_API_HASH": "fakehash",
    "OPENROUTER_API_KEY": "fake-openrouter-key",
}
for _k, _v in _ENV_DEFAULTS.items():
    os.environ.setdefault(_k, _v)


def _make_fetcher():
    """Create a HistoricalMessageFetcher with fully mocked dependencies."""
    # Patch the module-level imports that require external services
    with patch.dict('sys.modules', {
        'telethon': MagicMock(),
        'telethon.sessions': MagicMock(),
        'telethon.utils': MagicMock(),
        'psycopg2': MagicMock(),
        'psycopg2.extras': MagicMock(),
        'message_utils': MagicMock(),
    }):
        # Also patch config so the import doesn't fail
        mock_config = MagicMock()
        mock_config.DATABASE_URL = 'postgresql://test'
        with patch.dict('sys.modules', {'config': mock_config}):
            from historical_message_fetcher import HistoricalMessageFetcher

    mock_db = MagicMock()
    mock_client = MagicMock()
    fetcher = HistoricalMessageFetcher(mock_db, mock_client)
    return fetcher


class TestGetDatabaseStats(unittest.TestCase):
    """Tests for HistoricalMessageFetcher.get_database_stats()"""

    def _build_fetcher_with_cursor(self, row):
        """
        Build a HistoricalMessageFetcher whose DB returns `row` from
        cursor.fetchone().  Returns (fetcher,).
        """
        from historical_message_fetcher import HistoricalMessageFetcher

        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        # Wire the context-manager chain: db.get_connection() -> conn -> cursor
        mock_db.get_connection.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = row

        mock_client = MagicMock()
        fetcher = HistoricalMessageFetcher(mock_db, mock_client)
        return fetcher

    def _make_real_dict_row(self):
        """
        Return a MagicMock that behaves like a psycopg2 RealDictRow,
        i.e. supports row['col_name'] access but raises TypeError on row[0].
        """
        data = {
            'total': 100,
            'unprocessed': 20,
            'processed': 75,
            'processing': 3,
            'failed': 2,
            'oldest': '2024-01-01T00:00:00',
            'newest': '2024-03-01T00:00:00',
            'groups': 5,
        }

        row = MagicMock()
        # Support row['key'] access
        row.__getitem__.side_effect = lambda key: data[key]
        # Accessing by integer index should raise TypeError (like a real RealDictRow)
        def getitem(key):
            if isinstance(key, int):
                raise TypeError("RealDictRow does not support integer index access")
            return data[key]
        row.__getitem__.side_effect = getitem

        return row, data

    def test_get_database_stats_uses_key_access(self):
        """
        get_database_stats() must access result columns by name (key),
        not by integer index — matching psycopg2 RealDictRow semantics.
        """
        row, expected_data = self._make_real_dict_row()
        fetcher = self._build_fetcher_with_cursor(row)

        stats = fetcher.get_database_stats()

        # The method should return a non-empty dict
        self.assertIsInstance(stats, dict)
        self.assertGreater(len(stats), 0)

        # Confirm key-based access was used (not integer access)
        # If integer access had been used, __getitem__ would have raised TypeError
        # and the method would have returned {}.
        for call in row.__getitem__.call_args_list:
            key = call[0][0]
            self.assertIsInstance(
                key, str,
                f"Expected string key access but got integer index: {key!r}"
            )

    def test_get_database_stats_returns_dict_with_expected_keys(self):
        """
        get_database_stats() must return a dict containing all expected keys.
        """
        row, expected_data = self._make_real_dict_row()
        fetcher = self._build_fetcher_with_cursor(row)

        stats = fetcher.get_database_stats()

        expected_keys = {
            'total', 'unprocessed', 'processed',
            'processing', 'failed', 'oldest', 'newest', 'groups'
        }
        self.assertTrue(
            expected_keys.issubset(stats.keys()),
            f"Missing keys: {expected_keys - stats.keys()}"
        )

    def test_get_database_stats_correct_values(self):
        """
        get_database_stats() must map DB column values to the returned dict correctly.
        """
        row, expected_data = self._make_real_dict_row()
        fetcher = self._build_fetcher_with_cursor(row)

        stats = fetcher.get_database_stats()

        for key, expected_value in expected_data.items():
            self.assertEqual(
                stats[key], expected_value,
                f"stats['{key}'] = {stats[key]!r}, expected {expected_value!r}"
            )

    def test_get_database_stats_returns_empty_dict_on_error(self):
        """
        get_database_stats() must return {} when an exception occurs,
        without propagating the error.
        """
        from historical_message_fetcher import HistoricalMessageFetcher

        mock_db = MagicMock()
        mock_db.get_connection.side_effect = RuntimeError("DB down")

        fetcher = HistoricalMessageFetcher(mock_db, MagicMock())
        stats = fetcher.get_database_stats()

        self.assertEqual(stats, {})


if __name__ == '__main__':
    unittest.main()
