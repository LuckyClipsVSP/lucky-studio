from flask import Flask, render_template, request, jsonify
import subprocess, os, json, time

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLIPS_FILE = os.path.join(BASE_DIR, "clips_prontos.json")
STATUS_FILE = os.path.join(BASE_DIR, "status.txt")

@app.route('/')
def index(): return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    link = request.json.get('link')
    with open(CLIPS_FILE, "w", encoding="utf-8") as f: json.dump([], f)
    with open(STATUS_FILE, "w", encoding="utf-8") as f: 
        f.write(f"Iniciando análise de clips de 30s...|{int(time.time())}")
    
    subprocess.Popen(['python3', os.path.join(BASE_DIR, 'pipeline.py'), link])
    return jsonify({"status": "Processo iniciado para clips de 30 segundos"})

@app.route('/get_status')
def get_status():
    try:
        with open(STATUS_FILE, "r") as f: raw = f.read().split('|')
        msg = raw[0]
        start_time = raw[1] if len(raw) > 1 else int(time.time())
        
        clips = []
        if os.path.exists(CLIPS_FILE):
            with open(CLIPS_FILE, "r") as f: clips = json.load(f)
        return jsonify({"status": msg, "start_time": start_time, "clips": clips})
    except: return jsonify({"status": "Aguardando...", "clips": []})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
