"""Deny PostgreSQL connections before application imports, including subprocesses.

Tests may replace psycopg.connect with a fake. Class-level connection entrypoints
remain denied so a missed mock cannot reach the actual driver.
"""
import psycopg


class PostgreSQLConnectionDenied(AssertionError):
    """An offline backend test attempted to open a PostgreSQL connection."""


def deny_connection(*args, **kwargs):
    # Do not print arguments: inherited configuration may contain real secrets.
    raise PostgreSQLConnectionDenied("Real PostgreSQL connections are forbidden in backend tests.")


async def deny_async_connection(*args, **kwargs):
    deny_connection()


def install_postgres_guard():
    psycopg.connect = deny_connection
    psycopg.Connection.connect = classmethod(deny_connection)
    psycopg.AsyncConnection.connect = classmethod(deny_async_connection)
