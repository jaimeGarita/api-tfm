from flask import Flask, render_template, request, session
import requests
from bs4 import BeautifulSoup
import pandas as pd
from waitress import serve
import random
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
import os
import boto3
import json

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_aqui'  # Necesario para usar sesiones

def get_db_credentials():
    try:
        # Si estamos en desarrollo local, usar variables de entorno
        if os.getenv('FLASK_ENV') == 'development':
            print("Usando credenciales de variables de entorno locales")
            return {
                'dbname': os.getenv('DB_NAME'),
                'username': os.getenv('DB_USER'),
                'password': os.getenv('DB_PASSWORD'),
                'host': os.getenv('DB_HOST'),
                'port': int(os.getenv('DB_PORT', '5432'))
            }
            
        # Si no estamos en desarrollo, intentar AWS Secrets Manager
        session = boto3.session.Session()
        client = session.client(
            service_name='secretsmanager',
            region_name='us-west-2'
        )
        
        secret_response = client.get_secret_value(
            SecretId='rds-credentials-db-1'
        )
        if secret_response:
            credentials = json.loads(secret_response['SecretString'])
            print("Credenciales obtenidas de AWS Secrets Manager")
            return credentials
        else:
            print("Advertencia: No se pudieron obtener las credenciales de AWS Secrets Manager")
            return None 
    except Exception as e:
        print(f"Error obteniendo credenciales: {str(e)}")
        return None

def get_db_connection():
    credentials = get_db_credentials()
    if not credentials:
        print("No se pudieron obtener las credenciales de la base de datos")
        return None
        
    try:
        conn = psycopg2.connect(
            dbname=credentials['dbname'],
            user=credentials['username'],
            password=credentials['password'],
            host=credentials['host'],
            port=credentials['port']
        )
        print(f"Conexión exitosa a la base de datos en {credentials['host']}")
        return conn
    except Exception as e:
        print(f"Error conectando a la base de datos: {str(e)}")
        return None

def init_db():
    try:
        conn = get_db_connection()
        if conn is None:
            print("No se pudo establecer conexión con la base de datos")
            return False
            
        with conn.cursor() as cur:
            cur.execute('''CREATE TABLE IF NOT EXISTS articulos
                       (id SERIAL PRIMARY KEY,
                        titulo TEXT,
                        url TEXT,
                        resumen TEXT,
                        longitud INTEGER,
                        num_referencias INTEGER,
                        categorias TEXT,
                        ultima_modificacion TEXT,
                        fecha_scraping TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
            conn.commit()
            print("Tabla 'articulos' creada o verificada exitosamente")
            return True
    except Exception as e:
        print(f"Error en init_db: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()
            print("Conexión cerrada")

def save_to_db(links):
    conn = get_db_connection()
    cur = conn.cursor()
    for link in links:
        cur.execute('''INSERT INTO articulos 
                      (titulo, url, resumen, longitud, num_referencias, 
                       categorias, ultima_modificacion)
                      VALUES (%s, %s, %s, %s, %s, %s, %s)''',
                   (link['titulo'], link['url'], link['resumen'],
                    link['longitud'], link['num_referencias'],
                    link['categorias'], link['ultima_modificacion']))
    conn.commit()
    cur.close()
    conn.close()

def get_historic_links(limit=None):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    if limit:
        cur.execute('SELECT * FROM articulos ORDER BY fecha_scraping DESC LIMIT %s', (limit,))
    else:
        cur.execute('SELECT * FROM articulos ORDER BY fecha_scraping DESC')
    links = cur.fetchall()
    cur.close()
    conn.close()
    return links

def get_article_info(url, headers):
    """Obtiene información detallada de un artículo"""
    try:
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Obtener el primer párrafo (resumen)
        first_p = soup.find('div', class_='mw-parser-output').find('p', class_=False)
        resumen = first_p.text.strip() if first_p else 'No disponible'
        
        # Obtener longitud del artículo
        content = soup.find(id='mw-content-text')
        longitud = len(content.text) if content else 0
        
        # Obtener fecha de última modificación
        ultima_mod = 'No disponible'
        footer = soup.find('li', id='footer-info-lastmod')
        if footer:
            ultima_mod = footer.text.replace('Esta página se editó por última vez el ', '').strip()
        
        # Obtener categorías
        categorias = []
        cat_links = soup.find_all('div', class_='mw-normal-catlinks')
        for cat in cat_links:
            cats = cat.find_all('a')
            categorias.extend([c.text for c in cats[1:]])  # Ignorar el primer enlace que es "Categorías"
        
        # Obtener referencias
        referencias = len(soup.find_all('cite')) if soup.find_all('cite') else 0
        
        return {
            'resumen': resumen,
            'longitud': longitud,
            'ultima_modificacion': ultima_mod,
            'categorias': '|'.join(categorias),
            'num_referencias': referencias
        }
    except Exception as e:
        print(f"Error obteniendo detalles de {url}: {str(e)}")
        return {
            'resumen': 'Error',
            'longitud': 0,
            'ultima_modificacion': 'Error',
            'categorias': 'Error',
            'num_referencias': 0
        }

def get_wiki_links(url='https://es.wikipedia.org/wiki/Wikipedia:Portada', num_links=10):
    # Headers para evitar bloqueos
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    links = []
    visited = set()
    to_visit = {url}
    
    while len(links) < num_links and to_visit:
        try:
            current_url = to_visit.pop()
            if current_url in visited:
                continue
                
            response = requests.get(current_url, headers=headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            content = soup.find(id='mw-content-text')
            if content:
                for a in content.find_all('a', href=True):
                    href = a['href']
                    if href.startswith('/wiki/') and ':' not in href and '#' not in href:
                        full_url = 'https://es.wikipedia.org' + href
                        if full_url not in visited and full_url not in to_visit:
                            article_info = get_article_info(full_url, headers)
                            
                            # Añadir fecha y hora actual de la búsqueda
                            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            
                            links.append({
                                'titulo': a.text.strip(),
                                'url': full_url,
                                'resumen': article_info['resumen'],
                                'longitud': article_info['longitud'],
                                'ultima_modificacion': article_info['ultima_modificacion'],
                                'categorias': article_info['categorias'],
                                'num_referencias': article_info['num_referencias'],
                                'fecha_scraping': current_time
                            })
                            to_visit.add(full_url)
                            print(f"Procesado: {len(links)}/{num_links}")
                            
                            if len(links) >= num_links:
                                break
            
            visited.add(current_url)
            
        except Exception as e:
            print(f"Error procesando {current_url}: {str(e)}")
            continue
    
    # Guardar en CSV solo si es una nueva búsqueda
    df = pd.DataFrame(links)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'wikipedia_links_{timestamp}.csv'
    df.to_csv(filename, index=False, encoding='utf-8')
    print(f'Enlaces guardados en {filename}')
            
    return links[:num_links]

@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'scrape':
            try:
                num_links = int(request.form.get('num_links', 100))
                links = get_wiki_links(num_links=num_links)
                session['links'] = links
                session['last_search'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                return render_template('index.html', 
                                    links=links, 
                                    show_form=True,
                                    search_time=session.get('last_search'))
            except Exception as e:
                return render_template('index.html', error=str(e), show_form=True)
        
        elif action == 'historic' or action == 'recent':
            links = session.get('links', [])
            if links:
                if action == 'recent' and request.form.get('limit'):
                    limit = int(request.form.get('limit', 100))
                    links = sorted(links, key=lambda x: x['fecha_scraping'], reverse=True)[:limit]
                return render_template('index.html', 
                                    links=links, 
                                    show_historic=True,
                                    search_time=session.get('last_search'))
            else:
                return render_template('index.html', 
                                    error="No hay búsquedas recientes en la sesión actual.", 
                                    show_form=True)
    
    return render_template('index.html', show_form=True)

@app.route('/reset', methods=['POST'])
def reset():
    """Endpoint para reiniciar la búsqueda"""
    session.pop('links', None)
    session.pop('last_search', None)
    return render_template('index.html', show_form=True)

if __name__ == '__main__':
    try:
        if os.getenv('FLASK_ENV') == 'development':
            print("Iniciando en modo desarrollo")
            if init_db():
                print("Base de datos inicializada correctamente")
            else:
                print("Advertencia: No se pudo inicializar la base de datos")
        else:
            if not init_db():
                print("Advertencia: No se pudo inicializar la base de datos")
                
        serve(app, host='0.0.0.0', port=5000)
    except Exception as e:
        print(f"Error al iniciar la aplicación: {str(e)}")