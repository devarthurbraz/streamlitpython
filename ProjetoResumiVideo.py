import os
import re
import json
import time
import urllib.request
import streamlit as st
import yt_dlp
import whisper
from google import genai
from dotenv import load_dotenv

DIR_SCRIPT = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(DIR_SCRIPT, ".env"), override=True)

LANG_PRIORIDADE = ['pt-BR', 'pt', 'pt-orig', 'en', 'en-US', 'es']

def _cookies():
    caminho = os.path.join(DIR_SCRIPT, "cookies.txt")
    return caminho if os.path.exists(caminho) else None

def _baixar_legenda(url):
    """Tenta obter legenda nativa/automática via yt-dlp. Retorna (texto, idioma) ou (None, None)."""
    opts = {
        'skip_download': True, 'writesubtitles': True, 'writeautomaticsub': True,
        'subtitleslangs': ['pt.*', 'en.*', 'es.*', 'all'], 'quiet': True, 'no_warnings': True,
    }
    if _cookies():
        opts['cookiefile'] = _cookies()

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        legendas = {**info.get('subtitles', {}), **info.get('automatic_captions', {})}
        if not legendas:
            return None, None

        lang = next((l for l in LANG_PRIORIDADE if l in legendas), next(iter(legendas)))
        formatos = legendas[lang]
        url_sub = next((f['url'] for f in formatos if f.get('ext') == 'json3'), formatos[0]['url'])

        conteudo = urllib.request.urlopen(url_sub).read().decode('utf-8')

        if url_sub.endswith('json3') or 'events' in conteudo:
            data = json.loads(conteudo)
            texto = " ".join(
                seg.get('utf8', '')
                for ev in data.get('events', []) for seg in ev.get('segs', [])
            )
            texto = " ".join(texto.split())
        else:
            linhas = re.sub(r'<[^>]+>', '', conteudo).splitlines()
            texto = " ".join(
                l.strip() for l in linhas
                if l.strip() and not l.startswith('WEBVTT') and '-->' not in l and not l.isdigit()
            )

        return texto, lang
    except Exception:
        return None, None

def _transcrever_audio(url):
    """Baixa o áudio e transcreve com Whisper. Retorna o texto transcrito."""
    base = os.path.join(DIR_SCRIPT, "temp_media")
    opts = {
        "quiet": True, "no_warnings": True, "check_formats": False, "noplaylist": True,
        "format": "bestaudio/best", "outtmpl": f"{base}.%(ext)s",
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
    }
    if _cookies():
        opts["cookiefile"] = _cookies()

    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.extract_info(url, download=True)

    caminho_audio = f"{base}.mp3"
    resultado = whisper.load_model("tiny").transcribe(caminho_audio)

    if os.path.exists(caminho_audio):
        os.remove(caminho_audio)

    return resultado["text"]

def extrair_texto_youtube_v2(url, status_placeholder):
    """Extrai o texto do vídeo: legenda nativa se existir, senão transcreve o áudio."""
    texto, idioma = _baixar_legenda(url)
    
    if texto and len(texto.strip()) > 50:
        status_placeholder.markdown("✅ **Legenda encontrada, trasncrição será rápida..**")
        return texto, f"Legenda Nativa ({idioma})"

    status_placeholder.markdown("⚠️ **Transcrevendo via Áudio pode demorar um poquinho mais...**")
    return _transcrever_audio(url), "Transcrição por Áudio (Whisper)"

def resumir_com_gemini(texto, status_placeholder):
    """Envia a transcrição para o Gemini com retentativas automáticas."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY não foi encontrada no arquivo .env")

    client = genai.Client(api_key=api_key)

    prompt = f"""
Você é um assistente especializado em resumir e organizar conteúdos educacionais e acadêmicos.

IDIOMA DE SAÍDA:
- O resumo deve ser fornecido obrigatoriamente em PORTUGUÊS.
REGRAS GERAIS DE ESTRUTURA:
1. Crie um resumo claro, estruturado com título principal (#), subtítulos (##) e tópicos (-).
2. Não invente informações. Elimine repetições.
3. Se houver um passo a passo, organize os itens em uma sequência numerada.
REGRAS OBRIGATÓRIAS PARA MATEMÁTICA E FÓRMULAS:
4. NUNCA utilize comandos brutos de LaTeX (EXEMPLOS PROIBIDOS: \\implies, \\end{{cases}}, \\begin{{matrix}}, \\\\, \\frac, $$, \\text).
5. Escreva equações e expressões matemáticas usando notação simples e legível em texto puro (exemplo: "3x - 3y = -15", "x = -1", "2x + 3y = 10").
6. Para mostrar implicações ou passos, use palavras simples como "resulta em", "logo", "portanto" ou a seta simples "->".
7. Escreva sistemas de equações linha por linha, de forma clara e separada, sem comandos de alinhamento LaTeX.
REGRAS DE CÓDIGO E CONCEITOS TÉCNICOS:
8. NUNCA traduza palavras-chave de programação (ex: 'if', 'else', 'for', 'return').
9. Corrija termos técnicos distorcidos por legendas automáticas.
TRANSCRIÇÃO / LEGENDA:
{texto}
"""

    for tentativa in range(1, 4):
        try:
            status_placeholder.markdown("🤖 **Gerando resumo com a IA...**")
            return client.models.generate_content(model="gemini-3.5-flash", contents=prompt).text
        except Exception as e:
            if "503" in str(e) or "UNAVAILABLE" in str(e):
                if tentativa < 3:
                    status_placeholder.markdown(f"⏳ **Servidor ocupado. Tentando novamente ({tentativa}/3)...**")
                    time.sleep(4)
                else:
                    raise Exception("O servidor da IA está temporariamente indisponível devido a alta demanda. Por favor, tente novamente em alguns minutos.")
            else:
                raise e

def main():
    st.set_page_config(page_title="Resumidor de Vídeos", page_icon="🎥", layout="wide")
    st.title("🎥 Resumidor do YouTube")
    st.write("Extraia transcrições e gere resumos organizados de aulas e tutoriais.")

    url = st.text_input("Link do vídeo do YouTube:", placeholder="https://www.youtube.com/watch?v=...")

    if st.button("Processar Vídeo", type="primary"):
        if not url:
            st.warning("Por favor, cole um link do YouTube antes de continuar.")
            return

        with st.status("Processando vídeo...", expanded=True) as status:
            try:
                status_placeholder = st.empty()
                texto_extraido, origem_texto = extrair_texto_youtube_v2(url, status_placeholder)
                resumo_final = resumir_com_gemini(texto_extraido, status_placeholder)

                status.update(label="Concluído! Clique para ver o resumo.", state="complete", expanded=False)

                aba_resumo, aba_texto = st.tabs(["📝 Resumo (PT)", "📄 Texto Bruto Extraído"])

                with aba_resumo:
                    st.markdown(resumo_final)
                    st.download_button("Baixar Resumo (.txt)", resumo_final, "resumo.txt", "text/plain")

                with aba_texto:
                    st.caption(f"Origem dos dados: {origem_texto}")
                    st.text_area("Texto extraído:", texto_extraido, height=300)
                    st.download_button("Baixar Texto Bruto (.txt)", texto_extraido, "transcricao.txt", "text/plain")

            except Exception as e:
                status.update(label="Ocorreu um erro durante o processamento.", state="error")
                st.error(f"Detalhes do erro: {e}")

if __name__ == "__main__":
    main()
