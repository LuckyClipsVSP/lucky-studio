from flask import Flask, request, jsonify, send_file
from pipeline import run_background # Importa a função de thread

app = Flask(__name__)

@app.route('/')
def index():
    return send_file('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    link = request.json.get('link')
    run_background(link) # Dispara o robô em segundo plano
    return jsonify({"status": "Processando na nuvem..."})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5001)))
