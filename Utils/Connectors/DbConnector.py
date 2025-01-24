import psycopg2
from psycopg2 import sql
from Utils.System import System

class DbConnector:
    def __init__(self):
        self.system = System()

    def get_connection(self):
        connection = psycopg2.connect(
            host=self.system.db_host,
            port=self.system.db_port,
            database=self.system.db_name,
            user=self.system.db_user,
            password=self.system.db_password
        )
        return connection