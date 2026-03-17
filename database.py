import mysql.connector
from mysql.connector import Error, pooling
from typing import Dict, List, Any, Optional, Union, Tuple
import jsonlog
from contextlib import contextmanager
import time
import config as env_config

logger = jsonlog.setup_logger("database")

mysql_config = env_config.Config(group="MYSQL")

default_config = {
    "host": mysql_config.get("MYSQL_HOST"),
    "user": mysql_config.get("MYSQL_USER"),
    "password": mysql_config.get("MYSQL_PASSWORD"),
    "database": mysql_config.get("MYSQL_DATABASE"),
    "port": 3306
}

class DatabaseClient:
    def __init__(self, config: Dict[str, Any] = default_config, use_pool: bool = False, pool_size: int = 5, max_retries: int = 3, database: Optional[str] = None):
        """
        Initialize MySQL client with connection parameters.
        
        Args:
            config: MySQL connection configuration (host, user, password, database, etc.)
            use_pool: Whether to use connection pooling
            pool_size: Size of the connection pool if pooling is enabled
            max_retries: Maximum number of connection retry attempts
        """
        self.config = config
        self.use_pool = use_pool
        self.pool_size = pool_size
        self.max_retries = max_retries
        self.connection = None
        self.pool = None
        self.logger = logger

        if self.use_pool:
            self._setup_connection_pool()
        
        
    def _setup_connection_pool(self):
        """Set up a connection pool for better performance."""
        try:
            self.pool = pooling.MySQLConnectionPool(
                pool_name="mysql_pool",
                pool_size=self.pool_size,
                **self.config
            )
            self.logger.info(f"Connection pool created with {self.pool_size} connections")
        except Error as e:
            self.logger.error(f"Error creating connection pool: {e}")
            raise
            
    @contextmanager
    def get_connection(self):
        """Get a connection from the pool or create a new one with retry logic."""
        connection = None
        retries = 0
        
        while retries < self.max_retries:
            try:
                if self.use_pool:
                    connection = self.pool.get_connection()
                else:
                    connection = mysql.connector.connect(**self.config)
                break
            except Error as e:
                retries += 1
                self.logger.warning(f"Connection attempt {retries}/{self.max_retries} failed: {e}")
                if retries >= self.max_retries:
                    self.logger.error("Maximum connection retry attempts reached. Config: {self.config}")
                    raise
                time.sleep(1)  # Wait before retrying
        
        try:
            yield connection
        finally:
            if connection:
                if self.use_pool:
                    connection.close()
                elif connection.is_connected():
                    connection.close()
                
    @contextmanager
    def connection_cursor(self, dictionary: bool = True):
        """
        Context manager for handling connection and cursor.
        
        Args:
            dictionary: Whether to return results as dictionaries
        """
        connection = None
        cursor = None
        try:
            with self.get_connection() as connection:
                cursor = connection.cursor(dictionary=dictionary)
                yield connection, cursor
        finally:
            if cursor:
                cursor.close()
                
    def execute_query(self, query: str, params: Optional[Union[Dict[str, Any], List[Any], Tuple[Any, ...]]] = None) -> List[Dict[str, Any]]:
        """
        Execute a SELECT query and return results as a list of dictionaries.
        
        Args:
            query: SQL query string
            params: Parameters for query binding to prevent SQL injection
            
        Returns:
            List of dictionaries where each dictionary represents a row
        """
        results = []
        with self.connection_cursor() as (connection, cursor):
            try:
                cursor.execute(query, params)
                results = cursor.fetchall()
                self.logger.debug(f"Query executed successfully: {query}")
            except Error as e:
                self.logger.error(f"Error executing query: {e}")
                raise
        return results
        
    def execute_update(self, query: str, params: Optional[Union[Dict[str, Any], List[Any], Tuple[Any, ...]]] = None) -> int:
        """
        Execute an INSERT, UPDATE, or DELETE query.
        
        Args:
            query: SQL query string
            params: Parameters for query binding to prevent SQL injection
            
        Returns:
            Number of affected rows
        """
        with self.connection_cursor() as (connection, cursor):
            try:
                cursor.execute(query, params)
                connection.commit()
                affected_rows = cursor.rowcount
                last_id = cursor.lastrowid
                self.logger.debug(f"Query executed successfully, affected rows: {affected_rows}")
                return affected_rows, last_id
            except Error as e:
                self.logger.error(f"Error executing query: {e}")
                connection.rollback()
                raise
                
    def execute_many(self, query: str, params: List[Union[Dict[str, Any], List[Any], Tuple[Any, ...]]]) -> int:
        """
        Execute multiple INSERT, UPDATE, or DELETE queries at once.
        
        Args:
            query: SQL query string with placeholders
            params: List of parameter sets for query binding
            
        Returns:
            Number of affected rows
        """
        with self.connection_cursor() as (connection, cursor):
            try:
                cursor.executemany(query, params)
                connection.commit()
                affected_rows = cursor.rowcount
                self.logger.debug(f"Executemany successful, affected rows: {affected_rows}")
                return affected_rows
            except Error as e:
                self.logger.error(f"Error executing many queries: {e}")
                connection.rollback()
                raise
                
    def fetch_one(self, query: str, params: Optional[Union[Dict[str, Any], List[Any], Tuple[Any, ...]]] = None) -> Optional[Dict[str, Any]]:
        """
        Execute a SELECT query and return a single row as a dictionary.
        
        Args:
            query: SQL query string
            params: Parameters for query binding to prevent SQL injection
            
        Returns:
            A dictionary representing a single row or None if no results
        """
        with self.connection_cursor() as (connection, cursor):
            try:
                cursor.execute(query, params)
                result = cursor.fetchone()
                return result
            except Error as e:
                self.logger.error(f"Error executing query: {e}")
                raise
                
    def fetch_value(self, query: str, params: Optional[Union[Dict[str, Any], List[Any], Tuple[Any, ...]]] = None) -> Any:
        """
        Execute a SELECT query and return a single value.
        
        Args:
            query: SQL query string
            params: Parameters for query binding to prevent SQL injection
            
        Returns:
            A single value from the first column of the first row or None if no results
        """
        with self.connection_cursor(dictionary=False) as (connection, cursor):
            try:
                cursor.execute(query, params)
                result = cursor.fetchone()
                return result[0] if result else None
            except Error as e:
                self.logger.error(f"Error executing query: {e}")
                raise
                
    @contextmanager
    def transaction(self):
        """
        Context manager for handling transactions.
        """
        connection = None
        cursor = None
        try:
            with self.get_connection() as connection:
                cursor = connection.cursor(dictionary=True)
                yield cursor
                connection.commit()
        except Error as e:
            if connection:
                connection.rollback()
                self.logger.error(f"Transaction rolled back due to error: {e}")
            raise
        finally:
            if cursor:
                cursor.close()
    def is_connected(self) -> bool:
        """
        Check if the connection to the database is active.
        """
        try:
            with self.get_connection() as connection:
                return connection.is_connected()
        except Error:
            return False

    def close(self):
        """Close the MySQL connection."""
        if not self.use_pool and self.connection and self.connection.is_connected():
            self.connection.close()
            self.logger.info("MySQL connection closed")