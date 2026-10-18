import os
import time
import json
import subprocess
from flask import Flask, request, jsonify, send_file

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLIPS_FILE = os.path.join(BASE_DIR, "clips_prontos.json")
STATUS_FILE = os.path.join(BASE_DIR, "status.txt")
INDEX_PATH = os.path.join(BASE_DIR, "index.html")

@app.route('/')
def index():
    return send_file(INDEX_PATH) if os.path.exists(INDEX_PATH) else "Erro: index.html nao encontrado"

@app.route('/generate', methods=['POST'])
def generate():
    link = request.json.get('link')
    with open(CLIPS_FILE, "w", encoding="utf-8") as f: json.dump([], f)
    with open(STATUS_FILE, "w", encoding="utf-8") as f: f.write(f"Iniciando...|{int(time.time())}")
    
    # FORMA ROBUSTA: Chamada direta via python3 -u (o -u força a saída do log aparecer no console)
    subprocess.Popen(['python3', '-u', os.path.join(BASE_DIR, 'pipeline.py'), link])
    return jsonify({"status": "Processo iniciado"})

@app.route('/get_status')
def get_status():
    try:
        msg = "Processando..."
        start_time = int(time.time())
        if os.path.exists(STATUS_FILE):
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                raw = f.read().split('|')
                msg = raw[0]
                if len(raw) > 1: start_time = int(raw[1])
        clips = json.load(open(CLIPS_FILE)) if os.path.exists(CLIPS_FILE) else []
        return jsonify({"status": msg, "start_time": start_time, "clips": clips})
    except: return jsonify({"status": "Processando...", "clips": []})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5001)))
