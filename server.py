import os
import time
import json
import subprocess
from flask import Flask, request, jsonify, send_file

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLIPS_FILE = os.path.join(BASE_DIR, "clips_prontos.json")
STATUS_FILE = os.path.join(BASE_DIR, "status.txt")
INDEX_PATH = os.path.join(BASE_DIR, "index.html")

app = Flask(__name__)

@app.route('/')
def index():
    if os.path.exists(INDEX_PATH):
        return send_file(INDEX_PATH)
    return "Arquivo index.html nao encontrado na raiz do projeto.", 404

@app.route('/generate', methods=['POST'])
def generate():
    data = request.get_json() or {}
    link = data.get('link')
    if not link:
        return jsonify({"error": "Link ausente"}), 400

    # Reseta o estado dos arquivos temporarios
    with open(CLIPS_FILE, "w", encoding="utf-8") as f:
        json.dump([], f)
    
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        f.write(f"1/4. [Protocolo /Watch] Analisando contexto...|{int(time.time())}")

    # Executa o pipeline de fundo sem travar o servidor Flask
    subprocess.Popen(['python3', os.path.join(BASE_DIR, 'pipeline.py'), link])
    return jsonify({"status": "Processo iniciado para clips de 30 segundos"})

@app.route('/get_status')
def get_status():
    try:
        msg = "Aguardando..."
        start_time = int(time.time())
        if os.path.exists(STATUS_FILE):
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                raw = f.read().split('|')
                msg = raw[0]
                if len(raw) > 1:
                    start_time = int(raw[1])

        clips = []
        if os.path.exists(CLIPS_FILE):
            with open(CLIPS_FILE, "r", encoding="utf-8") as f:
                clips = json.load(f)

        return jsonify({"status": msg, "start_time": start_time, "clips": clips})
    except Exception as e:
        return jsonify({"status": f"Processando... ({str(e)})", "clips": []})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)
