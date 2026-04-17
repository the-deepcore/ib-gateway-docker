from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Optional

import pandas as pd
import psycopg2

# ============================================================================
# Connection configuration
# ============================================================================

@dataclass
class PostgresConfig:
    """
    Configuration for connecting to PostgreSQL.
    
    Attributes:
        host: Server address 
        port: PostgreSQL port 
        database: Database name
        username: Username for authentication
        password: Password for authentication
    """
    host: str = "localhost"
    port: int = 5432
    database: str = "thedeepcore_dev"
    username: str = "postgres"
    password: str = ""
    
    @classmethod
    def from_env(cls) -> PostgresConfig:
        """
        Create a config from environment variables.
        
        Environment variables used:
            - POSTGRES_HOST (or PGHOST)
            - POSTGRES_PORT (or PGPORT)
            - POSTGRES_DATABASE (or PGDATABASE)
            - POSTGRES_USERNAME (or PGUSER)
            - POSTGRES_PASSWORD (or PGPASSWORD)
        """
        return cls(
            host=os.getenv("POSTGRES_HOST", os.getenv("PGHOST", "localhost")),
            port=int(os.getenv("POSTGRES_PORT", os.getenv("PGPORT", "5432"))),
            database=os.getenv("POSTGRES_DATABASE", os.getenv("PGDATABASE", "trading_db")),
            username=os.getenv("POSTGRES_USERNAME", os.getenv("PGUSER", "postgres")),
            password=os.getenv("POSTGRES_PASSWORD", os.getenv("PGPASSWORD", "")),
        )


# ============================================================================
# Connection manager 
# ============================================================================

class PostgresConnection:
    """
    PostgreSQL connection manager.   
    """
    
    def __init__(self, config: PostgresConfig):
        """
        Initialize with configuration.
        
        Args:
            config: The PostgreSQL configuration
        """
        self.config = config
    
    def db_connect(self) -> psycopg2.extensions.connection:
        """
        Create a new connection to the database.
        
        Returns a psycopg2 connection object.
        """
        return psycopg2.connect(
            dbname=self.config.database,
            user=self.config.username,
            password=self.config.password,
            host=self.config.host,
            port=self.config.port
        )
    
    def select_from_query(self, query: str) -> pd.DataFrame:
        """
        Execute a SELECT query and return results as a DataFrame.
        
        Args:
            query: SQL SELECT query
        
        Returns:
            DataFrame with query results
        """
        import warnings
        
        conn = self.db_connect()
        
        try:
            # Suppress pandas warning about DBAPI2 (psycopg2 works fine)
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")
                df = pd.read_sql(query, conn)
        finally:
            conn.close()
        
        return df

    def execute_write_querry(self, query: str, params: tuple = ()) -> None:
        """
        Execute a write query (INSERT, UPDATE, DELETE) with commit.
        
        Args:
            query: SQL query with %s placeholders for parameters
            params: Tuple of parameter values
        """
        conn = self.db_connect()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
        finally:
            conn.close()

    def test_connection(self) -> bool:
        """
        Test if the database connection works.
        
        Returns True if connection is OK, False otherwise.
        """
        try:
            conn = self.db_connect()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            conn.close()
            return True
        except Exception as e:
            print(f"PostgreSQL connection error: {e}")
            return False




_global_connection: Optional[PostgresConnection] = None


def init_postgres(config: Optional[PostgresConfig] = None) -> PostgresConnection:
    """
    Initialize the global PostgreSQL connection.
    
    Args:
        config: The configuration. If None, uses environment variables.
    
    Returns:
        The PostgreSQL connection instance.
    """
    global _global_connection
    
    if config is None:
        config = PostgresConfig.from_env()
    
    _global_connection = PostgresConnection(config)
    return _global_connection


def get_postgres() -> PostgresConnection:
    """
    Get the global PostgreSQL connection.
    
    Raises:
        RuntimeError: If init_postgres() was not called before.
    """
    if _global_connection is None:
        raise RuntimeError(
            "PostgreSQL not initialized. "
            "Call init_postgres(config) first."
        )
    return _global_connection
