import mysql.connector as m
from dotenv import dotenv_values
e=dotenv_values(".env")
g=lambda *ks: next((v for k,v in e.items() if any(x in k.upper() for x in ks)),None)
c=m.connect(host=g("HOST"),user=g("USER"),password=g("PASS"),connect_timeout=10)
cur=c.cursor()
cur.execute("SHOW FULL PROCESSLIST")
me=c.connection_id
u=g("USER")
for r in cur.fetchall():
    if r[0]!=me and r[1]==u:
        print("cerrando",r[0],r[4],r[5],r[6])
        try: cur.execute("KILL %d"%r[0])
        except Exception as ex: print(ex)
print("listo")
