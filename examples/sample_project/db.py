"""
File 4: db.py — Fake database layer (in-memory, no connection pooling).
"""
import time
import random


class FakeDatabase:
    def __init__(self):
        self.data = {}
        self.connections = 0
        self.max_connections = 5

    def connect(self):
        self.connections += 1
        time.sleep(random.uniform(0.01, 0.05))  # simulate connection time
        if self.connections > self.max_connections:
            raise ConnectionError("Database connection pool exhausted!")

    def disconnect(self):
        self.connections = max(0, self.connections - 1)

    def execute_query(self, query: str):
        time.sleep(random.uniform(0.01, 0.1))
        return {"result": "ok", "query": query}

    def fetch_all(self, table: str):
        return self.data.get(table, [])

    def insert(self, table: str, record: dict):
        if table not in self.data:
            self.data[table] = []
        self.data[table].append(record)
        return len(self.data[table])


database = FakeDatabase()

# Documented code

# Documented code
