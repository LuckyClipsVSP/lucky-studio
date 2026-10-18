import os
import sys
import json
import time
import requests
import threading
from concurrent.futures import ThreadPoolExecutor
import cloudinary
import cloudinary.uploader
import cloudinary.utils

# ---------------------------------------------------------
# CONFIGURAÇÕES E CHAVES
# ---------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATUS_FILE = os.path.join(BASE_DIR, "status.txt")
CLIPS_FILE = os.path.join(BASE_DIR, "clips_prontos.json")

# Nova chave do Gemini configurada
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "AQ.Ab8RN6Kh80Opo-tH-JXLisEQYf_c_I5pN64PVNjP1GIqDfpd6w")
COBALT_URL = os.environ.get("COBALT_URL", "https://cobalt-production-aaf4.up.railway.app")

cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key=os.environ.get("CLOUDINARY_API_KEY"),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
    secure=True
)

file_lock = threading.Lock()

def log(msg):
    print(f"[LOG] {msg}")
    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            start_time = f.read().split('|')[1]
    except Exception:
        start_time = int(time.time())
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        f.write(f"{msg}|{start_time}")

def salvar_clipes(clips):
    with file_lock:
        try:
            with open(CLIPS_FILE, "w", encoding="utf-8") as f:
                json.dump(clips, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[ERRO JSON]: {e}")

# ---------------------------------------------------------
# 1. ANÁLISE COM O GEMINI IA (SUPORTE COMPLETO À CHAVE AQ.)
# ---------------------------------------------------------
def analisar_com_gemini(youtube_url):
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
    
    # Headers com suporte nativo a chaves Vertex / Cloud Console (AQ.)
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_KEY
    }
    
    prompt = f"""
    Você é um editor profissional de Shorts/TikTok/Reels virais.
    Analise o contexto deste vídeo: {youtube_url}
    Selecione os 3 momentos mais marcantes, engraçados ou de retenção máxima de exatamente 30 segundos.
    Responda EXCLUSIVAMENTE em formato JSON puro, sem blocos markdown:
    [
      {{"start": 30, "title": "MOMENTO INACREDITÁVEL", "legenda": "VOCÊ NÃO VAI ACREDITAR"}},
      {{"start": 75, "title": "O SEGREDO REVELADO", "legenda": "PRESTE MUITA ATENÇÃO"}},
      {{"start": 130, "title": "FINAL SURPREENDENTE", "legenda": "OLHA O QUE ACONTECEU"}}
    ]
    """
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2}
    }
    
    try:
        # Tenta primeiro com header x-goog-api-key, e depois via query param se necessário
        resp = requests.post(url, headers=headers, json=payload, timeout=35)
        if resp.status_code != 200:
            resp = requests.post(f"{url}?key={GEMINI_KEY}", json=payload, timeout=35)

        if resp.status_code == 200:
            data = resp.json()
            texto = data['candidates'][0]['content']['parts'][0]['text']
            inicio = texto.find("[")
            fim = texto.rfind("]") + 1
            cortes = json.loads(texto[inicio:fim])
            print("[GEMINI SUCESSO] Momentos virais gerados pela IA!")
            return cortes
        else:
            print(f"[AVISO GEMINI] Status {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[AVISO GEMINI EXCEÇÃO]: {e}")

    # Fallback caso a API do Google demore ou oscile
    print("[GEMINI] Usando cortes padrão de alta conversão...")
    return [
        {"start": 30, "title": "MOMENTO BIZARRO", "legenda": "VOCÊ NÃO VAI ACREDITAR"},
        {"start": 75, "title": "SURREAL DEMAIS", "legenda": "OLHA O QUE ACONTECEU"},
        {"start": 130, "title": "FINAL INESPERADO", "legenda": "INACREDITÁVEL"}
    ]

# ---------------------------------------------------------
# 2. EXTRAÇÃO VIA COBALT (SEU RAILWAY + FALLBACK PÚBLICO)
# ---------------------------------------------------------
def obter_link_direto_cobalt(youtube_url):
    tentativas = [
        f"{COBALT_URL.rstrip('/')}/",
        f"{COBALT_URL.rstrip('/')}/api/json",
        "https://api.cobalt.tools/"
    ]
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    payload = {
        "url": youtube_url,
        "videoQuality": "720"
    }

    for ep in tentativas:
        try:
            print(f"[COBALT] Tentando rota: {ep}")
            res = requests.post(ep, json=payload, headers=headers, timeout=30)
            if res.status_code == 200:
                dados = res.json()
                stream = dados.get("url")
                if stream:
                    print(f"[COBALT SUCESSO] Link obtido com sucesso via {ep}")
                    return stream
            else:
                print(f"[COBALT AVISO] Resposta {res.status_code} de {ep}")
        except Exception as e:
            print(f"[COBALT FALHA {ep}]: {e}")
            continue

    return None

# ---------------------------------------------------------
# 3. EDIÇÃO E RENDERIZAÇÃO NO CLOUDINARY
# ---------------------------------------------------------
def renderizar_corte(dados):
    i, corte, stream_url = dados
    try:
        start_sec = int(corte.get("start", 30))
        titulo = corte.get("title", "DESTAQUE").upper().replace(",", "").replace("/", "").replace(":", "")
        legenda = corte.get("legenda", "CONFIRA").upper().replace(",", "").replace("/", "").replace(":", "")
        
        print(f"[Corte {i}] Recortando aos {start_sec}s e renderizando no Cloudinary...")
        
        transformations = [
            {"start_offset": start_sec, "duration": 30},
            {"width": 1080, "height": 1920, "crop": "fill", "gravity": "face"},
            {
                "overlay": {"font_family": "Arial", "font_size": 42, "font_weight": "bold", "text": titulo},
                "color": "#00D4FF",
                "gravity": "north",
                "y": 140
            },
            {
                "overlay": {"font_family": "Arial", "font_size": 48, "font_weight": "bold", "text": legenda},
                "color": "#FFFF00",
                "gravity": "south",
                "y": 180
            }
        ]
        
        upload = cloudinary.uploader.upload_large(
            stream_url,
            resource_type="video",
            folder="viral_shorts",
            transformation=transformations,
            overwrite=True
        )
        
        url_final = upload.get("secure_url")
        print(f"[Corte {i}] Pronto: {url_final}")
        
        with file_lock:
            try:
                with open(CLIPS_FILE, "r", encoding="utf-8") as f:
                    status_atual = json.load(f)
                status_atual[i].update({"url": url_final, "status": "pronto"})
                salvar_clipes(status_atual)
            except Exception as e:
                print(f"[ERRO ATUALIZAÇÃO STATUS]: {e}")
                
    except Exception as e:
        print(f"[ERRO CLOUDINARY CORTE {i}]: {e}")
        with file_lock:
            try:
                with open(CLIPS_FILE, "r", encoding="utf-8") as f:
                    status_atual = json.load(f)
                status_atual[i].update({"status": "erro", "erro": str(e)})
                salvar_clipes(status_atual)
            except Exception:
                pass

# ---------------------------------------------------------
# FLUXO PRINCIPAL
# ---------------------------------------------------------
def run():
    if len(sys.argv) < 2:
        return
    
    youtube_url = sys.argv[1]
    
    log("1/4. [Gemini IA] Analisando o contexto do vídeo...")
    cortes = analisar_com_gemini(youtube_url)
    
    log("2/4. [Cobalt] Extraindo vídeo em alta velocidade...")
    stream_url = obter_link_direto_cobalt(youtube_url)
    
    if not stream_url:
        log("ERRO: Não foi possível obter o link do vídeo pelo Cobalt.")
        return

    lista_inicial = [{"id": i, "title": c["title"], "url": "", "status": "renderizando"} for i, c in enumerate(cortes)]
    salvar_clipes(lista_inicial)
    
    log("3/4. [Cloudinary] Editando e recortando em 9:16 com Auto-Framing...")
    
    tarefas = [(i, c, stream_url) for i, c in enumerate(cortes)]
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(renderizar_corte, tarefas))
        
    log("4/4. Concluído! Seus vídeos estão prontos.")

if __name__ == "__main__":
    run()
