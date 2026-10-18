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

# Chave informada para o Gemini
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "AQ.Ab8RN6JZulamkSotT8nTIAA78b7k4naGfKspQDHMMrV9CdGdSg")
COBALT_API = "https://cobalt-production-aaf4.up.railway.app"

# Cloudinary (puxa das variáveis do Render)
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
# 1. ANÁLISE COM O GOOGLE GEMINI
# ---------------------------------------------------------
def analisar_com_gemini(youtube_url):
    """Pede ao Gemini para analisar o vídeo e extrair 3 trechos virais."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    
    prompt = f"""
    Você é um editor profissional de vídeos curtos (Shorts/TikTok/Reels).
    Analise o contexto deste vídeo: {youtube_url}
    Selecione os 3 momentos mais marcantes, engraçados ou de retenção máxima de exatamente 30 segundos.
    Responda EXCLUSIVAMENTE em formato JSON puro, sem blocos markdown:
    [
      {{"start": 30, "title": "TITULO IMPACTANTE 1", "legenda": "LEGENDA CHAMATIVA 1"}},
      {{"start": 90, "title": "TITULO IMPACTANTE 2", "legenda": "LEGENDA CHAMATIVA 2"}},
      {{"start": 150, "title": "TITULO IMPACTANTE 3", "legenda": "LEGENDA CHAMATIVA 3"}}
    ]
    """
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2}
    }
    
    try:
        resp = requests.post(url, json=payload, timeout=40)
        data = resp.json()
        texto = data['candidates'][0]['content']['parts'][0]['text']
        inicio = texto.find("[")
        fim = texto.rfind("]") + 1
        return json.loads(texto[inicio:fim])
    except Exception as e:
        print(f"[AVISO GEMINI]: Falha ou chave incompatível ({e}). Usando cortes estratégicos padrão.")
        return [
            {"start": 30, "title": "MOMENTO BIZARRO", "legenda": "VOCÊ NÃO VAI ACREDITAR"},
            {"start": 90, "title": "SURREAL DEMAIS", "legenda": "OLHA O QUE ACONTECEU"},
            {"start": 150, "title": "INACREDITÁVEL", "legenda": "FINAL INESPERADO"}
        ]

# ---------------------------------------------------------
# 2. OBTER STREAM DIRETO VIA COBALT (SEU RAILWAY)
# ---------------------------------------------------------
def obter_link_direto_cobalt(youtube_url):
    """Pede o link do arquivo de vídeo limpo para o seu Cobalt no Railway."""
    try:
        payload = {
            "url": youtube_url,
            "videoQuality": "720",
            "filenameStyle": "classic"
        }
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        res = requests.post(COBALT_API, json=payload, headers=headers, timeout=45)
        dados = res.json()
        return dados.get("url")
    except Exception as e:
        print(f"[ERRO COBALT]: {e}")
        return None

# ---------------------------------------------------------
# 3. EDIÇÃO E RENDERIZAÇÃO NO CLOUDINARY
# ---------------------------------------------------------
def renderizar_corte(dados):
    i, corte, stream_url = dados
    try:
        start_sec = int(corte.get("start", 30))
        titulo = corte.get("title", "DESTAQUE").upper().replace(",", "").replace("/", "")
        legenda = corte.get("legenda", "CONFIRA").upper().replace(",", "").replace("/", "")
        
        print(f"[Corte {i}] Enviando instruções para Cloudinary...")
        
        # O Cloudinary faz o recorte no tempo exato, foca no rosto e adiciona as legendas
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
        
        with file_lock:
            try:
                with open(CLIPS_FILE, "r", encoding="utf-8") as f:
                    status_atual = json.load(f)
                status_atual[i].update({"url": url_final, "status": "pronto"})
                salvar_clipes(status_atual)
            except Exception as e:
                print(f"[ERRO ATUALIZAÇÃO SUCESSO]: {e}")
                
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
    
    log("2/4. [Cobalt Railway] Extraindo link de alta velocidade sem bloqueios...")
    stream_url = obter_link_direto_cobalt(youtube_url)
    
    if not stream_url:
        log("ERRO: Não foi possível obter o link do vídeo pelo Cobalt.")
        return

    # Registra estado inicial dos clipes na interface
    lista_inicial = [{"id": i, "title": c["title"], "url": "", "status": "renderizando"} for i, c in enumerate(cortes)]
    salvar_clipes(lista_inicial)
    
    log("3/4. [Cloudinary] Editando e recortando em 9:16 com Auto-Framing...")
    
    tarefas = [(i, c, stream_url) for i, c in enumerate(cortes)]
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(renderizar_corte, tarefas))
        
    log("4/4. Concluído! Seus vídeos estão prontos.")

if __name__ == "__main__":
    run()
