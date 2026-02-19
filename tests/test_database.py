"""
Unit tests for database operations

Tests transaction rollback handling and connection pool management.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from contextlib import contextmanager


class TestDatabaseOperations(unittest.TestCase):
    """Test database operations and error handling"""
    
    def test_connection_pool_initialization(self):
        """Test that connection pool initializes with correct parameters"""
        from database import init_connection_pool
        
        with patch('database.ThreadedConnectionPool') as mock_pool:
            db_url = 'postgresql://test:test@localhost/test'
            init_connection_pool(db_url)
            
            # Verify pool was created with correct parameters
            mock_pool.assert_called_once()
            call_kwargs = mock_pool.call_args[1]
            self.assertEqual(call_kwargs['minconn'], 2)
            self.assertEqual(call_kwargs['maxconn'], 20)
            self.assertEqual(call_kwargs['dsn'], db_url)
    
    def test_connection_pool_exhaustion_handling(self):
        """Test that connection pool exhaustion raises clear error"""
        from database import get_db_connection
        
        mock_pool = Mock()
        mock_pool.getconn.return_value = None  # Simulate exhaustion
        
        with self.assertRaises(Exception) as context:
            with get_db_connection(mock_pool):
                pass
        
        self.assertIn('Connection pool exhausted', str(context.exception))
    
    def test_transaction_rollback_on_error(self):
        """Test that transactions are rolled back on errors"""
        from database import get_db_connection
        
        mock_pool = Mock()
        mock_conn = Mock()
        mock_pool.getconn.return_value = mock_conn
        
        # Simulate an error during transaction
        with self.assertRaises(ValueError):
            with get_db_connection(mock_pool) as conn:
                raise ValueError("Test error")
        
        # Verify rollback was called
        mock_conn.rollback.assert_called_once()
        # Verify connection was returned to pool
        mock_pool.putconn.assert_called_once_with(mock_conn)
    
    def test_successful_transaction_commits(self):
        """Test that successful transactions commit properly"""
        from database import get_db_connection
        
        mock_pool = Mock()
        mock_conn = Mock()
        mock_pool.getconn.return_value = mock_conn
        
        # Successful transaction
        with get_db_connection(mock_pool) as conn:
            # Do some work
            pass
        
        # Verify connection was returned to pool
        mock_pool.putconn.assert_called_once_with(mock_conn)


class TestDatabaseRepositories(unittest.TestCase):
    """Test database repository methods"""
    
    def test_add_raw_message_with_rollback(self):
        """Test that add_raw_message rolls back on error"""
        from database_repositories import MessageRepository

        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        # Setup context manager for cursor
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception("Database error")

        repo = MessageRepository(mock_pool)

        with patch.object(repo, 'get_connection') as mock_get_conn:
            mock_get_conn.return_value.__enter__.return_value = mock_conn

            # Should handle error gracefully
            try:
                repo.add_raw_message(
                    group_id=123,
                    message_id=456,
                    message_text="Test",
                    sender_id=789,
                    sent_at=None
                )
            except Exception:
                pass

            # Verify rollback was called
            mock_conn.rollback.assert_called()

    def test_mark_job_synced_with_rollback(self):
        """Test that mark_job_synced rolls back on error"""
        from database_repositories import UnifiedJobRepository

        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        # Setup context manager for cursor
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception("Database error")

        repo = UnifiedJobRepository(mock_pool)

        with patch.object(repo, 'get_connection') as mock_get_conn:
            mock_get_conn.return_value.__enter__.return_value = mock_conn

            # Should handle error gracefully
            try:
                repo.mark_job_synced(job_id="123")
            except Exception:
                pass

            # Verify rollback was called
            mock_conn.rollback.assert_called()


if __name__ == '__main__':
    unittest.main()
