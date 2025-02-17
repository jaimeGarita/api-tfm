from flask import Flask, render_template, request, session, jsonify
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
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_aqui'

DB_CONFIG = {
    'dbname': os.environ.get('DB_NAME', 'demodb'),
    'user': os.environ.get('DB_USER', 'demouser'),
    'password': os.environ.get('DB_PASSWORD', 'Demo1234!'),
    'host': os.environ.get('DB_HOST', 'aurora-cluster-demo.cluster-cnoge4wscm2u.us-west-2.rds.amazonaws.com'),
    'port': os.environ.get('DB_PORT', '5432')
}

def get_db_credentials():
    """Obtiene las credenciales de la base de datos según el entorno"""
    if os.getenv('FLASK_ENV') == 'development':
        print("Usando configuración local de base de datos desde variables de entorno")
        return {
            'dbname': os.getenv('DB_NAME', DB_CONFIG['dbname']),
            'user': os.getenv('DB_USER', DB_CONFIG['user']),
            'password': os.getenv('DB_PASSWORD', DB_CONFIG['password']),
            'host': os.getenv('DB_HOST', DB_CONFIG['host']),
            'port': os.getenv('DB_PORT', DB_CONFIG['port'])
        }
    
    try:
        # Configuración para AWS Secrets Manager en producción
        session = boto3.session.Session()
        client = session.client(
            service_name='secretsmanager',
            region_name=os.getenv('AWS_REGION', 'us-west-2')
        )
        
        secret_name = os.getenv('AWS_SECRET_NAME', 'rds-credentials-db-1')
        secret_response = client.get_secret_value(SecretId=secret_name)
        db_credentials = json.loads(secret_response['SecretString'])
        
        return {
            'dbname': db_credentials.get('dbname', DB_CONFIG['dbname']),
            'user': db_credentials.get('username', DB_CONFIG['user']),
            'password': db_credentials.get('password', DB_CONFIG['password']),
            'host': db_credentials.get('host', DB_CONFIG['host']),
            'port': str(db_credentials.get('port', DB_CONFIG['port']))
        }
    except Exception as e:
        print(f"Error obteniendo credenciales de Secrets Manager: {str(e)}")
        return DB_CONFIG

def get_db_connection():
    logger.info("Intentando conectar a la base de datos...")
    try:
        conn = psycopg2.connect(**get_db_credentials())
        logger.info("Conexión exitosa a la base de datos")
        return conn
    except Exception as e:
        logger.error(f"Error conectando a la base de datos: {str(e)}")
        raise

def init_db():
    logger.info("Initializing database...")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''CREATE TABLE IF NOT EXISTS articles
                    (id SERIAL PRIMARY KEY,
                     title TEXT,
                     url TEXT UNIQUE,
                     summary TEXT,
                     length INTEGER,
                     num_references INTEGER,
                     categories TEXT,
                     last_modification TEXT,
                     date_scraping TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.commit()
        logger.info("Table 'articles' created/verified successfully")
        cur.close()
        conn.close()
    except Exception as e:
        logger.error(f"Error in init_db: {str(e)}")
        raise

def save_to_db(links):
    logger.info(f"Intentando guardar {len(links)} artículos en la base de datos...")
    conn = get_db_connection()
    cur = conn.cursor()
    saved_count = 0
    
    try:
        for link in links:
            cur.execute('''
                INSERT INTO articles 
                (title, url, summary, length, num_references, 
                 categories, last_modification)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id''',
                (link['titulo'], 
                 link['url'], 
                 link['resumen'],
                 link['longitud'], 
                 link['num_referencias'],
                 link['categorias'], 
                 link['ultima_modificacion']))
            saved_count += 1
            
        conn.commit()
        logger.info(f"Guardados exitosamente {saved_count} artículos en la base de datos")
    except Exception as e:
        conn.rollback()
        logger.error(f"Error guardando en la base de datos: {str(e)}")
        raise
    finally:
        cur.close()
        conn.close()

def get_historic_links(limit=None):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    if limit:
        cur.execute('SELECT * FROM articles ORDER BY date_scraping DESC LIMIT %s', (limit,))
    else:
        cur.execute('SELECT * FROM articles ORDER BY date_scraping DESC')
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
    logger.info(f"Iniciando web scraping para {num_links} enlaces...")
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
    
    # Después de obtener los links, guardarlos en la base de datos
    try:
        save_to_db(links[:num_links])
    except Exception as e:
        logger.error(f"Error al guardar los enlaces en la base de datos: {str(e)}")
    
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

def insert_article(title, url, summary, length=0, num_references=0, categories='', last_modification=''):
    """Insert a single article if the URL doesn't exist in the database"""
    logger.info(f"Attempting to insert article: {title}")
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # First check if URL exists
        cur.execute('SELECT id FROM articles WHERE url = %s', (url,))
        if cur.fetchone():
            logger.info(f"Article with URL {url} already exists. Skipping insertion.")
            return False

        # If URL doesn't exist, proceed with insertion
        cur.execute('''
            INSERT INTO articles 
            (title, url, summary, length, num_references, categories, last_modification)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id''',
            (title, url, summary, length, num_references, categories, last_modification))
        
        article_id = cur.fetchone()[0]
        conn.commit()
        logger.info(f"Article successfully inserted with ID: {article_id}")
        return True

    except Exception as e:
        conn.rollback()
        logger.error(f"Error inserting article: {str(e)}")
        raise
    finally:
        cur.close()
        conn.close()

def get_articles(limit=None, order_by='date_scraping', order='DESC'):
    """Get articles with flexible filtering options"""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        query = 'SELECT * FROM articles'
        params = []

        # Add ordering
        query += f' ORDER BY {order_by} {order}'

        # Add limit if specified
        if limit:
            query += ' LIMIT %s'
            params.append(limit)

        cur.execute(query, params)
        articles = cur.fetchall()
        return articles

    except Exception as e:
        logger.error(f"Error fetching articles: {str(e)}")
        raise
    finally:
        cur.close()
        conn.close()

@app.route('/update_article', methods=['POST'])
def update_article():
    try:
        data = request.get_json()
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('''
            UPDATE articles 
            SET title = %s, summary = %s, categories = %s
            WHERE id = %s
            RETURNING id''',
            (data['title'], data['summary'], data['categories'], data['id']))
        
        updated_id = cur.fetchone()
        conn.commit()
        
        if updated_id:
            return jsonify({'success': True, 'message': 'Artículo actualizado correctamente'})
        else:
            return jsonify({'success': False, 'message': 'No se encontró el artículo'}), 404
            
    except Exception as e:
        logger.error(f"Error actualizando artículo: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/delete_article', methods=['POST'])
def delete_article():
    try:
        data = request.get_json()
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('DELETE FROM articles WHERE id = %s RETURNING id', (data['id'],))
        deleted_id = cur.fetchone()
        conn.commit()
        
        if deleted_id:
            return jsonify({'success': True, 'message': 'Artículo eliminado correctamente'})
        else:
            return jsonify({'success': False, 'message': 'No se encontró el artículo'}), 404
            
    except Exception as e:
        logger.error(f"Error eliminando artículo: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    try:
        # Inicializar la base de datos
        init_db()
        print("Base de datos inicializada correctamente")
        
        # Iniciar la aplicación
        if os.getenv('FLASK_ENV') == 'development':
            print("Iniciando en modo desarrollo")
            app.run(debug=True, host="0.0.0.0", port=5000)
        else:
            print("Iniciando en modo producción")
            serve(app, host="0.0.0.0", port=5000)
            
    except Exception as e:
        print(f"Error al iniciar la aplicación: {str(e)}")