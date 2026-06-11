import sqlite3

DATABASE_NAME = "aria.db"

def connect_db():
    return sqlite3.connect(DATABASE_NAME)