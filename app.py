from flask import Flask, render_template, request, redirect, url_for, send_file
import pandas as pd
from data_processing import clean_dataframe
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import io
from waitress import serve

# Crea una instancia de Flask
app = Flask(__name__)

def get_category(articulo, soup):
    """
    Extrae la categoría del artículo analizando diferentes elementos del DOM
    """
    # Primero intentamos obtener la categoría desde el div de la sección
    categoria_div = articulo.find('div', class_='a_k')
    if categoria_div:
        categoria_link = categoria_div.find('a', class_='a_k_n')
        if categoria_link:
            return categoria_link.text.strip()
    
    # Si no encontramos la categoría en el div, buscamos en las etiquetas de navegación
    try:
        # Buscar la URL del artículo
        articulo_url = articulo.find('a')['href']
        if articulo_url:
            # Extraer la sección de la URL
            partes_url = articulo_url.split('/')
            if len(partes_url) > 3:
                seccion = partes_url[3]  # Ejemplo: internacional, economia, deportes, etc.
                
                # Mapeo de secciones principales
                secciones = {
                    'internacional': 'Internacional',
                    'economia': 'Economía',
                    'deportes': 'Deportes',
                    'sociedad': 'Sociedad',
                    'cultura': 'Cultura',
                    'tecnologia': 'Tecnología',
                    'gente': 'Gente',
                    'television': 'Televisión',
                    'espana': 'España',
                    'opinion': 'Opinión',
                    'america': 'América',
                    'mexico': 'México',
                    'us': 'Estados Unidos'
                }
                
                return secciones.get(seccion, seccion.capitalize())
    except:
        pass
    
    return 'No disponible'

def get_date(articulo):
    """
    Extrae la fecha del artículo desde el elemento sc_date
    """
    try:
        # Buscar específicamente el enlace con id="sc_date"
        fecha_elemento = articulo.find('a', id='a_md_f')
        if fecha_elemento:
            # Obtener la fecha del atributo data-date
            fecha_completa = fecha_elemento.get('data-date')
            if fecha_completa:
                return fecha_completa
            
            # Si no hay data-date, obtener el texto
            fecha_texto = fecha_elemento.text.strip()
            if fecha_texto:
                return fecha_texto
        
        # Búsqueda alternativa si no se encuentra el sc_date
        time_elemento = articulo.find('time')
        if time_elemento:
            return time_elemento.get('datetime', 'No disponible')
            
    except Exception as e:
        pass
    
    return 'No disponible'

def scrape_elpais():
    # URL del sitio web
    url = 'https://elpais.com'
    
    # Realizar la petición HTTP
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    response = requests.get(url, headers=headers)
    
    # Crear objeto BeautifulSoup
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Lista para almacenar los datos
    noticias = []
    
    # Encontrar todos los artículos
    articulos = soup.find_all('article')
    
    for articulo in articulos:
        titulo_elemento = articulo.find('h2')
        if titulo_elemento:
            titulo = titulo_elemento.text.strip()
            
            # Obtener enlace
            enlace_elemento = articulo.find('a')
            enlace = enlace_elemento.get('href') if enlace_elemento else 'No disponible'
            if enlace and not enlace.startswith('http'):
                enlace = 'https://elpais.com' + enlace
            
            # Obtener categoría del enlace
            categoria = 'No disponible'
            if enlace and 'elpais.com/' in enlace:
                partes_url = enlace.split('/')
                if len(partes_url) > 3:
                    # La categoría suele estar después del dominio
                    categoria = partes_url[3].replace('-', ' ').title()
            
            # Obtener resumen
            resumen_elemento = articulo.find('p', class_='c_d')
            if not resumen_elemento:
                resumen_elemento = articulo.find('h2', class_='a_st')
                print(resumen_elemento)
            resumen = resumen_elemento.text.strip() if resumen_elemento else 'No disponible'
            
            # Obtener autor
            autores = []
            autor_links = articulo.find_all('a', class_='c_a_a')
            if autor_links:
                autores = [autor.text.strip() for autor in autor_links]
                autor = ', '.join(autores)
            else:
                autor = 'No disponible'
            
            noticias.append({
                'categoria': categoria,
                'titulo': titulo,
                'resumen': resumen,
                'autor': autor,
                'enlace': enlace
            })
    
    # Crear DataFrame
    df = pd.DataFrame(noticias)
    
    # Guardar en CSV con timestamp
    fecha_actual = datetime.now().strftime('%Y%m%d_%H%M')
    nombre_archivo = f'noticias_elpais_{fecha_actual}.csv'
    df.to_csv(nombre_archivo, index=False, encoding='utf-8')
    
    print(f'Se han guardado {len(noticias)} noticias en {nombre_archivo}')
    return df

# Define una ruta para la página principal
@app.route('/', methods=['GET', 'POST'])
def hello():
    if request.method == 'POST':
        if 'scrape' in request.form:
            # Si se presiona el botón de scraping
            try:
                df = scrape_elpais()
                resultado_limpieza = clean_dataframe(df)
                
                # Generar archivo CSV para descarga
                output = io.StringIO()
                df.to_csv(output, index=False)
                output.seek(0)
                
                return render_template('index.html',
                                     estadisticas=resultado_limpieza,
                                     tabla=df.to_html(classes='table table-striped'),
                                     hay_datos=True)
            
            except Exception as e:
                return f'Error durante el scraping: {str(e)}'
        
        elif 'file' in request.files:
            file = request.files['file']
            if file.filename == '':
                return 'No se seleccionó ningún archivo'
            
            if file and file.filename.endswith('.csv'):
                df = pd.read_csv(file)
                resultado_limpieza = clean_dataframe(df)
                return render_template('index.html',
                                     estadisticas=resultado_limpieza,
                                     tabla=df.to_html(classes='table table-striped'),
                                     hay_datos=True)
            else:
                return 'Por favor, sube un archivo CSV'
    
    return render_template('index.html', hay_datos=False)

@app.route('/descargar-csv')
def descargar_csv():
    df = scrape_elpais()
    output = io.StringIO()
    df.to_csv(output, index=False)
    output.seek(0)
    
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'noticias_elpais_{datetime.now().strftime("%Y%m%d_%H%M")}.csv'
    )

# Inicia el servidor web
if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5000)