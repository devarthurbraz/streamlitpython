import os
import re
import json
import time
import streamlit as st
import yt_dlp
import whisper
from google import genai
from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi

# --- CONFIGURAÇÕES E AMBIENTE ---
DIR_SCRIPT = os.path.dirname(os.path.abspath(__file__))
caminho_env = os.path.join(DIR_SCRIPT, ".env")
load_dotenv(dotenv_path=caminho_env, override=True)


def extrair_texto_youtube_v2(url, status_placeholder):
    """
    1. Tenta extrair a transcrição instantaneamente via youtube-transcript-api.
    2. Se falhar, tenta via yt-dlp buscando metadados/legendas.
    3. Se não houver legendas, realiza o download do áudio e transcreve via Whisper.
    """
    status_placeholder.markdown("🔍 **Buscando legendas do vídeo...**")

    # Extrai o ID do vídeo a partir da URL
    video_id_match = re.search(r"(?:v=|\/([0-9A-Za-z_-]{11}))", url)
    video_id = video_id_match.group(1) if video_id_match else None

    # --- MÉTODO 1: API de Transcrição Direta (Rápido e sem bloqueios 403) ---
    if video_id:
        try:
            transcript_list = YouTubeTranscriptApi.get_transcript(
                video_id, languages=['pt', 'pt-BR', 'pt-orig', 'en', 'en-US', 'es']
            )
            texto_legenda = " ".join([item['text'] for item in transcript_list])
            if len(texto_legenda.strip()) > 50:
                status_placeholder.markdown("✅ **Legenda extraída com sucesso via API!**")
                return texto_legenda, "Legenda Direta (YouTube API)"
        except Exception:
            pass  # Se não houver legendas via API, prossegue para os métodos via yt-dlp

    # --- MÉTODO 2: yt-dlp (Metadados e Legendas) ---
    caminho_cookies = os.path.join(DIR_SCRIPT, "cookies.txt")
    cookies_param = caminho_cookies if os.path.exists(caminho_cookies) else None

    ydl_opts_sub = {
        'skip_download': True,
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitleslangs': ['pt.*', 'en.*', 'es.*', 'all'],
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios', 'web']
            }
        }
    }

    if cookies_param:
        ydl_opts_sub['cookiefile'] = cookies_param

    texto_legenda = None
    idioma_encontrado = None

    try:
        with yt_dlp.YoutubeDL(ydl_opts_sub) as ydl:
            info = ydl.extract_info(url, download=False)
            
            subtitles = info.get('subtitles', {})
            auto_subtitles = info.get('automatic_captions', {})
            todas_legendas = {**subtitles, **auto_subtitles}

            if todas_legendas:
                lang_prioridade = ['pt-BR', 'pt', 'pt-orig', 'en', 'en-US', 'es']
                lang_escolhida = None

                for lang in lang_prioridade:
                    if lang in todas_legendas:
                        lang_escolhida = lang
                        break

                if not lang_escolhida:
                    lang_escolhida = list(todas_legendas.keys())[0]

                formats = todas_legendas[lang_escolhida]
                url_sub = None
                
                for fmt in formats:
                    if fmt.get('ext') == 'json3':
                        url_sub = fmt.get('url')
                        break
                if not url_sub and formats:
                    url_sub = formats[0].get('url')

                if url_sub:
                    import urllib.request
                    req = urllib.request.urlopen(url_sub)
                    conteudo = req.read().decode('utf-8')

                    if url_sub.endswith('json3') or 'events' in conteudo:
                        data = json.loads(conteudo)
                        linhas = []
                        for event in data.get('events', []):
                            for seg in event.get('segs', []):
                                linhas.append(seg.get('utf8', ''))
                        texto_legenda = " ".join("".join(linhas).split())
                    else:
                        linhas = re.sub(r'<[^>]+>', '', conteudo).splitlines()
                        linhas_limpas = [l.strip() for l in linhas if l.strip() and not l.startswith('WEBVTT') and '-->' not in l and not l.isdigit()]
                        texto_legenda = " ".join(linhas_limpas)

                    idioma_encontrado = lang_escolhida

    except Exception:
        pass

    if texto_legenda and len(texto_legenda.strip()) > 50:
        status_placeholder.markdown("✅ **Legenda encontrada, transcrição será rápida..**")
        return texto_legenda, f"Legenda Nativa ({idioma_encontrado})"

    # --- MÉTODO 3: Whisper (Download de Áudio - Fallback) ---
    status_placeholder.markdown("⚠️ **Transcrevendo via Áudio (pode demorar um pouquinho mais)...**")

    saida_base = os.path.join(DIR_SCRIPT, "temp_media")

    opts_audio = {
        "quiet": True,
        "no_warnings": True,
        "check_formats": False,
        "noplaylist": True,
        "format": "ba/ba*",
        "outtmpl": f"{saida_base}.%(ext)s",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
        "extractor_args": {
            "youtube": {
                "player_client": ["ios", "mweb"]
            }
        },
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
        }
    }

    if cookies_param:
        opts_audio["cookiefile"] = cookies_param

    with yt_dlp.YoutubeDL(opts_audio) as ydl:
        ydl.extract_info(url, download=True)

    caminho_audio = f"{saida_base}.mp3"

    modelo_whisper = whisper.load_model("tiny")
    resultado = modelo_whisper.transcribe(caminho_audio)
    texto_transcrito = resultado["text"]

    if os.path.exists(caminho_audio):
        os.remove(caminho_audio)

    return texto_transcrito, "Transcrição por Áudio (Whisper)"


def resumir_com_gemini(texto, status_placeholder):
    """
    Envia a transcrição para o Gemini com retentativas automáticas
    e regras estritas para evitar formatação LaTeX quebrada.
    """
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

    max_tentativas = 3
    atraso_segundos = 4

    for tentativa in range(1, max_tentativas + 1):
        try:
            status_placeholder.markdown("🤖 **Gerando resumo com a IA...**")
            response = client.models.generate_content(
                model="gemini-3.5-flash",
                contents=prompt,
            )
            return response.text
        except Exception as e:
            msg_erro = str(e)
            if "503" in msg_erro or "UNAVAILABLE" in msg_erro:
                if tentativa < max_tentativas:
                    status_placeholder.markdown(f"⏳ **Servidor ocupado. Tentando novamente ({tentativa}/{max_tentativas})...**")
                    time.sleep(atraso_segundos)
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
        else:
            with st.status("Processando vídeo...", expanded=True) as status:
                try:
                    status_placeholder = st.empty()

                    texto_extraido, origem_texto = extrair_texto_youtube_v2(url, status_placeholder)

                    resumo_final = resumir_com_gemini(texto_extraido, status_placeholder)

                    status.update(label="Concluído! Clique para ver o resumo.", state="complete", expanded=False)

                    aba_resumo, aba_texto = st.tabs(["📝 Resumo (PT)", "📄 Texto Bruto Extraído"])

                    with aba_resumo:
                        st.markdown(resumo_final)
                        st.download_button(
                            label="Baixar Resumo (.txt)",
                            data=resumo_final,
                            file_name="resumo.txt",
                            mime="text/plain"
                        )

                    with aba_texto:
                        st.caption(f"Origem dos dados: {origem_texto}")
                        st.text_area("Texto extraído:", texto_extraido, height=300)
                        st.download_button(
                            label="Baixar Texto Bruto (.txt)",
                            data=texto_extraido,
                            file_name="transcricao.txt",
                            mime="text/plain"
                        )

                except Exception as e:
                    status.update(label="Ocorreu um erro durante o processamento.", state="error")
                    st.error(f"Detalhes do erro: {e}")


if __name__ == "__main__":
    main()
