import requests, sys, json, time, os, subprocess, random, threading
from concurrent.futures import ThreadPoolExecutor

FREELLM_KEY = "freellmapi-959bf30a13aa6d21c2175a96fc3affc64c72325e12aef119"
CREATOMATE_KEY = "19cf6a86d8ed4510b187942153d4dae1e8af945e9fcc241f4c7b14956cb773f60b6656a0bb82f7c4f24772dbbfbc993f"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATUS_FILE = os.path.join(BASE_DIR, "status.txt")
CLIPS_FILE = os.path.join(BASE_DIR, "clips_prontos.json")

# Lock para proteger escrita no arquivo de status
status_lock = threading.Lock()
clips_lock = threading.Lock()

def log(msg):
    print(f"[LOG] {msg}")
    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f: start_time = f.read().split('|')[1]
    except: start_time = int(time.time())
    with open(STATUS_FILE, "w", encoding="utf-8") as f: f.write(f"{msg}|{start_time}")

def save_state(clips):
    with clips_lock:
        try:
            with open(CLIPS_FILE, "w", encoding="utf-8") as f: json.dump(clips, f, indent=2)
        except Exception as e:
            print(f"[ERRO SAVE_STATE]: {e}")

def baixar_e_hospedar_trecho(youtube_url, start_sec, duracao):
    temp_file = f"/tmp/corte_{start_sec}.mp4"
    if os.path.exists(temp_file):
        os.remove(temp_file)

    end_sec = start_sec + duracao
    h1, m1, s1 = start_sec // 3600, (start_sec % 3600) // 60, start_sec % 60
    h2, m2, s2 = end_sec // 3600, (end_sec % 3600) // 60, end_sec % 60
    section = f"*{h1:02d}:{m1:02d}:{s1:02d}-{h2:02d}:{m2:02d}:{s2:02d}"

    cmd = [
        "yt-dlp", "--js-runtimes", "node",
        "--download-sections", section,
        "--force-keyframes-at-cuts",
        "-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", temp_file,
        youtube_url
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)
    except subprocess.TimeoutExpired:
        print(f"[ERRO YT-DLP TIMEOUT]: Download section excedeu 5 minutos")
        return None
    except Exception as e:
        print(f"[ERRO YT-DLP]: {e}")
        return None

    if not os.path.exists(temp_file):
        print(f"[ERRO ARQUIVO NÃO ENCONTRADO]: {temp_file}")
        return None

    try:
        with open(temp_file, "rb") as f:
            data = {"reqtype": "fileupload"}
            files = {"fileToUpload": (os.path.basename(temp_file), f, "video/mp4")}
            res = requests.post("https://catbox.moe/user/api.php", data=data, files=files, timeout=120)

            if res.status_code == 200 and res.text.startswith("http"):
                cloud_url = res.text.strip()
                os.remove(temp_file)
                return cloud_url
            else:
                print(f"[ERRO CATBOX]: Status {res.status_code}, Response: {res.text[:200]}")
    except Exception as e:
        print(f"[ERRO UPLOAD NUVEM]: {e}")

    if os.path.exists(temp_file):
        os.remove(temp_file)
    return None

def renderizar_e_esperar(dados):
    i, corte, video_url = dados
    try:
        duracao = int(corte.get('duration', 30))
        start = int(corte['start'])

        print(f"[Corte {i}] Renderizando com protocolo /Watch + B-Roll + Zoom...")
        cloud_video_url = baixar_e_hospedar_trecho(video_url, start, duracao)

        if not cloud_video_url:
            with clips_lock:
                try:
                    with open(CLIPS_FILE, "r", encoding="utf-8") as f:
                        clips_status = json.load(f)
                    clips_status[i].update({"status": "erro"})
                    with open(CLIPS_FILE, "w", encoding="utf-8") as f:
                        json.dump(clips_status, f, indent=2)
                except Exception as e:
                    print(f"[ERRO ATUALIZACAO ERRO]: {e}")
            return

        termo_busca = corte.get('termo_imagem', 'viral moment')
        imagem_contexto_url = f"https://source.unsplash.com/featured/?{termo_busca}"

        payload = {
            "output_format": "mp4", "width": 1080, "height": 1920,
            "elements": [
                {
                    "type": "video", "source": cloud_video_url, "duration": duracao, "fit": "cover",
                    "scale": "118%", "x": "50%", "y": "50%"
                },
                {
                    "type": "text", "text": corte['title'].upper(), "fill_color": "#00d4ff", "y": "10%",
                    "font_weight": "900", "font_size": "45px",
                    "background_color": "rgba(0,0,0,0.85)", "width": "85%", "padding": "15px"
                },
                {
                    "type": "image", "source": imagem_contexto_url,
                    "x": "50%", "y": "45%", "width": "75%", "height": "40%", "fit": "cover",
                    "start": int(corte.get('imagem_start', 4)), "duration": 3.5,
                    "border_radius": "20px", "background_color": "rgba(0,0,0,0.8)"
                },
                {
                    "type": "text", "text": corte['legenda'].upper(), "fill_color": "#ffff00", "y": "85%",
                    "font_size": "55px", "font_weight": "900",
                    "background_color": "rgba(0,0,0,0.9)", "width": "90%", "padding": "20px",
                    "stroke_color": "#000000", "stroke_width": "4px"
                }
            ]
        }

        headers = {"Authorization": f"Bearer {CREATOMATE_KEY}", "Content-Type": "application/json"}
        r = requests.post("https://api.creatomate.com/v2/renders", headers=headers, json=payload, timeout=60)
        
        try:
            r_json = r.json()
        except:
            print(f"[Corte {i}] ERRO DECODIFICANDO RESPOSTA CREATOMATE: {r.text[:200]}")
            with clips_lock:
                try:
                    with open(CLIPS_FILE, "r", encoding="utf-8") as f:
                        clips_status = json.load(f)
                    clips_status[i].update({"status": "erro"})
                    with open(CLIPS_FILE, "w", encoding="utf-8") as f:
                        json.dump(clips_status, f, indent=2)
                except Exception as e:
                    print(f"[ERRO ATUALIZACAO ERRO]: {e}")
            return

        if isinstance(r_json, dict):
            rid = r_json.get('id')
        elif isinstance(r_json, list) and len(r_json) > 0:
            rid = r_json[0].get('id')
        else:
            rid = None

        if not rid:
            print(f"[Corte {i}] ERRO OBTENDO ID CREATOMATE: {r_json}")
            with clips_lock:
                try:
                    with open(CLIPS_FILE, "r", encoding="utf-8") as f:
                        clips_status = json.load(f)
                    clips_status[i].update({"status": "erro"})
                    with open(CLIPS_FILE, "w", encoding="utf-8") as f:
                        json.dump(clips_status, f, indent=2)
                except Exception as e:
                    print(f"[ERRO ATUALIZACAO ERRO]: {e}")
            return

        tentativas = 0
        while tentativas < 120:  # Aumentado para 10 minutos
            time.sleep(5)
            tentativas += 1
            try:
                chk = requests.get(f"https://api.creatomate.com/v2/renders/{rid}", headers=headers, timeout=30).json()
                status = chk.get('status')

                if status == 'succeeded':
                    video_url_final = chk.get('url')
                    with clips_lock:
                        try:
                            with open(CLIPS_FILE, "r", encoding="utf-8") as f:
                                clips_status = json.load(f)
                            clips_status[i].update({"url": video_url_final, "status": "pronto"})
                            with open(CLIPS_FILE, "w", encoding="utf-8") as f:
                                json.dump(clips_status, f, indent=2)
                        except Exception as e:
                            print(f"[ERRO ATUALIZACAO PRONTO]: {e}")
                    break
                elif status == 'failed':
                    erro_msg = chk.get('error', 'Erro desconhecido')
                    print(f"[Corte {i}] FALHA CREATOMATE: {erro_msg}")
                    with clips_lock:
                        try:
                            with open(CLIPS_FILE, "r", encoding="utf-8") as f:
                                clips_status = json.load(f)
                            clips_status[i].update({"status": "erro", "erro": erro_msg})
                            with open(CLIPS_FILE, "w", encoding="utf-8") as f:
                                json.dump(clips_status, f, indent=2)
                        except Exception as e:
                            print(f"[ERRO ATUALIZACAO FALHA]: {e}")
                    break
            except Exception as e:
                print(f"[Corte {i}] ERRO VERIFICACAO: {e}")
                continue
        else:
            print(f"[Corte {i}] TIMEOUT: Renderização excedeu 10 minutos")
            with clips_lock:
                try:
                    with open(CLIPS_FILE, "r", encoding="utf-8") as f:
                        clips_status = json.load(f)
                    clips_status[i].update({"status": "erro", "erro": "Timeout"})
                    with open(CLIPS_FILE, "w", encoding="utf-8") as f:
                        json.dump(clips_status, f, indent=2)
                except Exception as e:
                    print(f"[ERRO ATUALIZACAO TIMEOUT]: {e}")
    except Exception as e:
        print(f"[Corte {i}] EXCEÇÃO: {e}")
        with clips_lock:
            try:
                with open(CLIPS_FILE, "r", encoding="utf-8") as f:
                    clips_status = json.load(f)
                clips_status[i].update({"status": "erro", "erro": str(e)})
                with open(CLIPS_FILE, "w", encoding="utf-8") as f:
                    json.dump(clips_status, f, indent=2)
            except Exception as ex:
                print(f"[ERRO ATUALIZACAO EXCECAO]: {ex}")

def run():
    if len(sys.argv) < 2:
        return

    video_url = sys.argv[1]

    log("1/4. [Protocolo /Watch] Analisando contexto completo e mapeando B-Rolls...")
    prompt_gemini = f"""
    Atue como a skill avançada /watch de análise de vídeos virais.
    Analise o vídeo do YouTube: {video_url} em sua totalidade.
    Identifique os 3 melhores trechos de 30 segundos com foco em retenção máxima, ignorando propagandas.
    Para cada trecho, determine:
    - start: segundo inicial do corte.
    - duration: 30.
    - termo_imagem: palavra-chave em inglês do objeto/conceito visual citado no trecho para ilustrar na tela (ex: 'retro magazine', 'money stack').
    - imagem_start: segundo exato (dentro do clipe de 30s) em que a imagem deve aparecer na tela.
    Responda APENAS em JSON puro:
    [{{"start": 45, "duration": 30, "termo_imagem": "retro magazine", "imagem_start": 6}}, {{"start": 120, "duration": 30, "termo_imagem": "confused face", "imagem_start": 10}}]
    """

    try:
        res_gemini = requests.post("http://127.0.0.1:31415/v1/chat/completions", headers={"Authorization": f"Bearer {FREELLM_KEY}"},
                           json={"model": "auto", "messages": [{"role": "user", "content": prompt_gemini}]}, timeout=60)
        content_g = res_gemini.json()['choices'][0]['message']['content']
        cortes_brutos = json.loads(content_g[content_g.find("["):content_g.rfind("]")+1])
    except Exception as e:
        print(f"[ERRO GEMINI]: {e}")
        cortes_brutos = [
            {"start": 30, "duration": 30, "termo_imagem": "viral moment", "imagem_start": 5},
            {"start": 90, "duration": 30, "termo_imagem": "news broadcast", "imagem_start": 8},
            {"start": 150, "duration": 30, "termo_imagem": "shocked face", "imagem_start": 10}
        ]

    log("2/4. [Groq Engine] Sintetizando títulos virais e legendas irônicas...")
    cortes_enriquecidos = []

    for c in cortes_brutos:
        start = int(c.get('start', 30))
        duration = int(c.get('duration', 30))
        termo_img = c.get('termo_imagem', 'viral')
        img_start = int(c.get('imagem_start', 5))

        prompt_groq = f"""
        Atue como editor sênior de Shorts virais.
        Para o trecho do segundo {start} ao {start + duration}, crie:
        1. Um título ácido e chamativo para o topo.
        2. Uma legenda irônica para a base.
        Responda APENAS em JSON puro:
        {{"title": "Título Incrível", "legenda": "Legenda Irônica"}}
        """

        try:
            res_groq = requests.post("http://127.0.0.1:31415/v1/chat/completions", headers={"Authorization": f"Bearer {FREELLM_KEY}"},
                                   json={"model": "auto", "messages": [{"role": "user", "content": prompt_groq}]}, timeout=60)
            content_q = res_groq.json()['choices'][0]['message']['content']
            dados_ia = json.loads(content_q[content_q.find("{"):content_q.rfind("}")+1])
        except Exception as e:
            print(f"[ERRO GROQ]: {e}")
            dados_ia = {"title": "Momento Épico", "legenda": "Você não vai acreditar nisso!"}

        cortes_enriquecidos.append({
            "start": start,
            "duration": duration,
            "termo_imagem": termo_img,
            "imagem_start": img_start,
            "title": dados_ia.get("title", "Corte Viral"),
            "legenda": dados_ia.get("legenda", "Olha isso!")
        })

    clips_status = [{"id": i, "title": c['title'], "url": "", "status": "renderizando"} for i, c in enumerate(cortes_enriquecidos)]
    save_state(clips_status)

    log("3/4. Executando pipeline completo (/Watch + B-Roll + Render)...")

    with ThreadPoolExecutor(max_workers=3) as ex:
        list(ex.map(renderizar_e_esperar, [(i, c, video_url) for i, c in enumerate(cortes_enriquecidos)]))

    log("4/4. Concluído!")
    
    # Verificar se todos os cortes foram processados
    try:
        with open(CLIPS_FILE, "r", encoding="utf-8") as f:
            final_status = json.load(f)
        prontos = sum(1 for c in final_status if c['status'] == 'pronto')
        erros = sum(1 for c in final_status if c['status'] == 'erro')
        if erros > 0:
            log(f"AVISO: {erros} cortes com erro de {len(final_status)} total")
    except:
        pass

if __name__ == "__main__":
    run()