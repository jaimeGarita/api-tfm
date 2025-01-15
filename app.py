from flask import Flask

# Crea una instancia de Flask
app = Flask(__name__)

# Define una ruta para la página principal
@app.route('/')
def hello():
    return '¡Hola, mundo desde Flask!'

# Inicia el servidor web
if __name__ == '__main__':
    app.run(debug=True)