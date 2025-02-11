import psycopg2
import os
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

def test_connection():
    try:
        # Obtener credenciales desde variables de entorno
        conn = psycopg2.connect(
            dbname=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            host='aurora-cluster-demo.cluster-cnoge4wscm2u.us-west-2.rds.amazonaws.com',  # Endpoint correcto del cluster
            port=int(os.getenv('DB_PORT', '5432'))
        )
        
        # Crear un cursor
        cur = conn.cursor()
        
        # Ejecutar una consulta simple
        cur.execute('SELECT version();')
        
        # Obtener el resultado
        version = cur.fetchone()
        print("Conexión exitosa!")
        print(f"Versión de PostgreSQL: {version[0]}")
        
        # Cerrar cursor y conexión
        cur.close()
        conn.close()
        print("Conexión cerrada")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_connection()
