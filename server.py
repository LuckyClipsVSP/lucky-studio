import os, time, json, threading
from flask import Flask, request, jsonify, send_file
import pipeline # Importa o seu pipeline como um módulo

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLIPS_FILE = os.path.join(BASE_DIR, "clips_prontos.json")
STATUS_FILE = os.path.join(BASE_DIR, "status.txt")

@app.route('/')
def index():
    return send_file("index.html")

@app.route('/generate', methods=['POST'])
def generate():
    link = request.json.get('link')
    with open(CLIPS_FILE, "w", encoding="utf-8") as f: json.dump([], f)
    with open(STATUS_FILE, "w", encoding="utf-8") as f: f.write("Iniciando...|"+str(int(time.time())))
    
    # Roda a função run() do pipeline.py em uma thread separada dentro do próprio servidor
    threading.Thread(target=pipeline.run_wrapper, args=(link,)).start()
    return jsonify({"status": "Processo iniciado"})

@app.route('/get_status')
def get_status():
    status = "Processando..."
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, "r") as f: status = f.read().split('|')[0]
    clips = json.load(open(CLIPS_FILE)) if os.path.exists(CLIPS_FILE) else []
    return jsonify({"status": status, "start_time": int(time.time()), "clips": clips})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
