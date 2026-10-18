from flask import Flask, request, jsonify, send_file
from pipeline import processar_viral

app = Flask(__name__)

@app.route('/')
def index(): return send_file('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    link = request.json.get('link')
    # Para testes iniciais, vamos rodar direto e ver se o erro aparece no log
    resultado = processar_viral(link)
    return jsonify({"status": "Concluído", "url": resultado})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
