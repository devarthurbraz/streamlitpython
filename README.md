# 🎥 Resumidor de Vídeos do YouTube

App em Python que extrai o conteúdo de um vídeo do YouTube (via legendas ou transcrição de áudio com Whisper) e gera um resumo estruturado usando a API do Gemini — tudo em uma interface web feita com Streamlit.

## Como funciona

1. Você cola o link de um vídeo do YouTube
2. O app tenta primeiro pegar a **legenda nativa/automática** do vídeo (mais rápido)
3. Se não houver legenda, ele **baixa o áudio e transcreve com Whisper**
4. O texto extraído é enviado para o **Gemini**, que gera um resumo estruturado em português
5. Você pode ver e baixar tanto o resumo quanto o texto bruto extraído

## Pré-requisitos

- [Python 3.10+](https://www.python.org/downloads/)
- [ffmpeg](https://ffmpeg.org/) instalado e configurado (necessário para extrair o áudio)
  - Windows: `winget install ffmpeg`
  - Linux: `sudo apt install ffmpeg`
  - Mac: `brew install ffmpeg`
- Uma chave de API do [Google Gemini](https://aistudio.google.com/apikey) (gratuita)

## Instalação

1. Clone o repositório:
```bash
git clone https://github.com/SEU-USUARIO/SEU-REPOSITORIO.git
cd SEU-REPOSITORIO
```

2. (Recomendado) Crie um ambiente virtual:
```bash
python -m venv venv
venv\Scripts\activate     # Windows
source venv/bin/activate  # Linux/Mac
```

3. Instale as dependências:
```bash
pip install streamlit yt-dlp openai-whisper google-genai python-dotenv
```

4. Crie um arquivo `.env` na raiz do projeto com sua chave da API:
```
GEMINI_API_KEY=sua_chave_aqui
```

## Como rodar

```bash
streamlit run ProjetoResumiVideo.py
```

O app vai abrir automaticamente no navegador (geralmente em `http://localhost:8501`).

## Cookies do YouTube (opcional)

Em alguns vídeos, o YouTube pode exigir confirmação de que você não é um robô. Se isso acontecer:

1. Instale a extensão **"Get cookies.txt LOCALLY"** no seu navegador
2. Acesse youtube.com logado na sua conta
3. Exporte os cookies e salve o arquivo como `cookies.txt` na raiz do projeto

O app detecta o arquivo automaticamente, se ele existir.

## Tecnologias usadas

- [Streamlit](https://streamlit.io/) — interface web
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — download de áudio e extração de legendas
- [OpenAI Whisper](https://github.com/openai/whisper) — transcrição de áudio
- [Google Gemini API](https://ai.google.dev/) — geração do resumo

## Aviso

Este projeto foi feito para fins de estudo. Respeite os Termos de Serviço do YouTube ao utilizá-lo.
