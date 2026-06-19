import sqlite3

conn = sqlite3.connect("aria.db")
cursor = conn.cursor()

cursor.execute("""
DELETE FROM memories
WHERE id NOT IN (
    SELECT MIN(id)
    FROM memories
    GROUP BY content
)
""")

conn.commit()
conn.close()

print("Duplicate Memories Removed")