import psycopg

# If your password contains @, encode it as %40 so the URL parser doesn't treat it as credential/host separator
DATABASE_URL = "postgresql://postgres:Loganmga201201%40@db.sfqkczhaqqqnnbvbpzaz.supabase.co:5432/postgres?sslmode=require"

conn = psycopg.connect(DATABASE_URL)

cur = conn.cursor()
cur.execute("SELECT 1;")

print("Connection successful:", cur.fetchone())

conn.close()