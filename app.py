from flask import Flask

# Crea una instancia de Flask
app = Flask(__name__)

# Define una ruta para la página principal
@app.route('/')
def hello():
<<<<<<< HEAD
    return '¡Hola, mundo desde Flask!'
=======
    return '¡Hola, mundo desde Flask! Prueba 2'
>>>>>>> feature/test-commit-codepipeline

# Nueva ruta para probar el pipeline
@app.route('/test')
def test():
    return '¡Pipeline funcionando correctamente!'

# Inicia el servidor web
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=False)