import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv
import os

load_dotenv(dotenv_path='.env')

class DbConnector:
    def __init__(self):
        self.__db_host = os.getenv("DB_HOST")
        self.__db_port = os.getenv("DB_PORT")
        self.__db_name = os.getenv("DB_NAME")
        self.__db_user = os.getenv("DB_USER")
        self.__db_password = os.getenv("DB_PASSWORD")

    def get_connection(self):
        connection = psycopg2.connect(
            host=self.__db_host,
            port=self.__db_port,
            database=self.__db_name,
            user=self.__db_user,
            password=self.__db_password
        )
        return connection