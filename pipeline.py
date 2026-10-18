import os
import sys
import json
import time
import requests
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
import cloudinary
import cloudinary.uploader
import cloudinary.utils

# -----------------------------------------------------------------------------
# CONFIGURAÇÕES E AMBIENTE NUVEM
# -----------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATUS_FILE = os.path.join(BASE_DIR, "status.txt")
CLIPS_FILE = os.path.join(BASE_DIR, "clips_prontos.json")

CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET", "")

if CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET:
    cloudinary.config(
        cloud_name=CLOUDINARY_CLOUD_NAME,
        api_key=CLOUDINARY_API_KEY,
        api_secret=CLOUDINARY_API_SECRET,
        secure=True
    )

clips_lock = threading.Lock()

def log(msg):
    print(f"[LOG] {msg}")
    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            start_time = f.read().split('|')[1]
    except Exception:
        start_time = int(time.time())
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        f.write(f"{msg}|{start_time}")

def save_state(clips):
    with clips_lock:
        try:
            with open(CLIPS_FILE, "w", encoding="utf-8") as f:
                json.dump(clips, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[ERRO SAVE_STATE]: {e}")

# -----------------------------------------------------------------------------
# EXTRAÇÃO DE MÍDIA COMPATÍVEL COM NUVEM
# -----------------------------------------------------------------------------
def baixar_trecho_local(youtube_url, start_sec, duracao):
    temp_file = f"/tmp/corte_{start_sec}_{int(time.time())}.mp4"
    if os.path.exists(temp_file):
        os.remove(temp_file)

    end_sec = start_sec + duracao
    h1, m1, s1 = start_sec // 3600, (start_sec % 3600) // 60, start_sec % 60
    h2, m2, s2 = end_sec // 3600, (end_sec % 3600) // 60, end_sec % 60
    section = f"*{h1:02d}:{m1:02d}:{s1:02d}-{h2:02d}:{m2:02d}:{s2:02d}"

    # Lista de estratégias de camuflagem (iOS, MWeb, TV) que não exigem login/cookies
    estrategias_clientes = [
        "youtube:player_client=ios,mweb",
        "youtube:player_client=tv_embedded",
        "youtube:player_client=mweb"
    ]

    for cliente in estrategias_clientes:
        cmd = [
            "yt-dlp",
            "--extractor-args", cliente,
            "--download-sections", section,
            "--force-keyframes-at-cuts",
            "-f", "b/best",
            "--no-check-certificates",
            "-o", temp_file,
            youtube_url
        ]
        
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if res.returncode == 0 and os.path.exists(temp_file) and os.path.getsize(temp_file) > 0:
                print(f"[YT-DLP SUCESSO] Recortado com cliente: {cliente}")
                return temp_file
            else:
                print(f"[YT-DLP TENTATIVA FALHOU ({cliente})]: {res.stderr[-200:]}")
        except Exception as e:
            print(f"[YT-DLP ERRO CLIENTE ({cliente})]: {e}")

    return temp_file if os.path.exists(temp_file) and os.path.getsize(temp_file) > 0 else None

# -----------------------------------------------------------------------------
# RENDERIZAÇÃO CLOUDINARY (ESTILO 9:16 + LEGENDAS)
# -----------------------------------------------------------------------------
def renderizar_cloudinary(dados):
    i, corte, video_url = dados
    try:
        duracao = int(corte.get('duration', 30))
        start = int(corte['start'])

        print(f"[Corte {i}] Recortando trecho do YouTube...")
        temp_video_path = baixar_trecho_local(video_url, start, duracao)

        if not temp_video_path:
            _marcar_erro(i, "Falha ao recortar vídeo com yt-dlp")
            return

        print(f"[Corte {i}] Enviando para o Cloudinary...")
        upload_res = cloudinary.uploader.upload_large(
            temp_video_path,
            resource_type="video",
            folder="viral_shorts",
            overwrite=True
        )
        
        if os.path.exists(temp_video_path):
            os.remove(temp_video_path)

        public_id = upload_res.get('public_id')

        titulo_texto = corte['title'].upper().replace(",", "").replace("/", "").replace(":", "")
        legenda_texto = corte['legenda'].upper().replace(",", "").replace("/", "").replace(":", "")

        transformations = [
            {"width": 1080, "height": 1920, "crop": "fill", "gravity": "face"},
            {
                "overlay": {
                    "font_family": "Arial", 
                    "font_size": 42, 
                    "font_weight": "bold", 
                    "text": titulo_texto
                },
                "color": "#00D4FF",
                "gravity": "north",
                "y": 140
            },
            {
                "overlay": {
                    "font_family": "Arial", 
                    "font_size": 48, 
                    "font_weight": "bold", 
                    "text": legenda_texto
                },
                "color": "#FFFF00",
                "gravity": "south",
                "y": 180
            }
        ]

        video_url_final, _ = cloudinary.utils.cloudinary_url(
            public_id,
            resource_type="video",
            format="mp4",
            transformation=transformations,
            secure=True
        )

        with clips_lock:
            try:
                with open(CLIPS_FILE, "r", encoding="utf-8") as f:
                    clips_status = json.load(f)
                clips_status[i].update({"url": video_url_final, "status": "pronto"})
                with open(CLIPS_FILE, "w", encoding="utf-8") as f:
                    json.dump(clips_status, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"[ERRO ATUALIZAÇÃO STATUS]: {e}")

    except Exception as e:
        print(f"[Corte {i}] EXCEÇÃO NO CLOUDINARY: {e}")
        _marcar_erro(i, str(e))

def _marcar_erro(index, erro_msg):
    with clips_lock:
        try:
            with open(CLIPS_FILE, "r", encoding="utf-8") as f:
                clips_status = json.load(f)
            clips_status[index].update({"status": "erro", "erro": erro_msg})
            with open(CLIPS_FILE, "w", encoding="utf-8") as f:
                json.dump(clips_status, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[ERRO ATUALIZAÇÃO ERRO]: {e}")

# -----------------------------------------------------------------------------
# CHAMADAS DE INTELIGÊNCIA ARTIFICIAL
# -----------------------------------------------------------------------------
def chamar_ia(prompt):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    
    key = os.environ.get("LLM_API_KEY", "")
    if key:
        headers["Authorization"] = f"Bearer {key}"

    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": "Responda exclusivamente em JSON puro."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code == 200:
            return resp.json()['choices'][0]['message']['content']
    except Exception:
        pass
    return None

def run():
    if len(sys.argv) < 2:
        return

    video_url = sys.argv[1]

    log("1/4. [Protocolo /Watch] Analisando contexto...")
    prompt_gemini = f"""
    Analise o vídeo do YouTube: {video_url}.
    Identifique os 3 melhores trechos de 30 segundos.
    Responda APENAS em JSON puro:
    [
      {{"start": 30, "duration": 30}},
      {{"start": 90, "duration": 30}},
      {{"start": 150, "duration": 30}}
    ]
    """

    res_ia = chamar_ia(prompt_gemini)
    try:
        cortes_brutos = json.loads(res_ia[res_ia.find("["):res_ia.rfind("]")+1])
    except Exception:
        cortes_brutos = [
            {"start": 30, "duration": 30},
            {"start": 90, "duration": 30},
            {"start": 150, "duration": 30}
        ]

    log("2/4. [Groq Engine] Sintetizando títulos virais e legendas...")
    cortes_enriquecidos = []

    for c in cortes_brutos:
        start = int(c.get('start', 30))
        duration = int(c.get('duration', 30))

        prompt_copy = f"""
        Para um Short viral do segundo {start} ao {start + duration}, crie:
        1. Título curto marcante.
        2. Legenda irônica e chamativa.
        Responda APENAS em JSON puro:
        {{"title": "MOMENTO INCRÍVEL", "legenda": "VOCÊ NÃO VAI ACREDITAR"}}
        """

        res_copy = chamar_ia(prompt_copy)
        try:
            dados_ia = json.loads(res_copy[res_copy.find("{"):res_copy.rfind("}")+1])
        except Exception:
            dados_ia = {"title": "MOMENTO VIRAL", "legenda": "OLHA ISSO AQUI"}

        cortes_enriquecidos.append({
            "start": start,
            "duration": duration,
            "title": dados_ia.get("title", "Corte Viral"),
            "legenda": dados_ia.get("legenda", "Veja isso!")
        })

    clips_status = [{"id": i, "title": c['title'], "url": "", "status": "renderizando"} for i, c in enumerate(cortes_enriquecidos)]
    save_state(clips_status)

    log("3/4. Executando edição 9:16 no Cloudinary...")

    with ThreadPoolExecutor(max_workers=3) as ex:
        list(ex.map(renderizar_cloudinary, [(i, c, video_url) for i, c in enumerate(cortes_enriquecidos)]))

    log("4/4. Concluído!")

if __name__ == "__main__":
    run()
