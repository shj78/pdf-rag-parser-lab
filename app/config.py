import os

from dotenv import load_dotenv

load_dotenv()

# 공급자 설정: ollama(로컬, 기본) | openai(클라우드, 선택)
PROVIDER = os.getenv("PROVIDER", "ollama").lower()

# Ollama 설정 (기본값 - 로컬 모델 사용)
OLLAMA_BASE = os.getenv("OLLAMA_BASE", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
OLLAMA_CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "llama3.1")

# OpenAI 설정
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")

# OpenAI 사용 시 필수 키 검증
if PROVIDER == "openai" and not OPENAI_API_KEY:
    raise ValueError(
        "PROVIDER=openai로 설정했지만 OPENAI_API_KEY가 설정되지 않았습니다."
    )

UPLOAD_DIR = "app/uploads"
TRACE_DIR = "app/traces"

try:
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR)
    if not os.path.exists(TRACE_DIR):
        os.makedirs(TRACE_DIR)
except OSError as e:
    raise RuntimeError(
        f"필수 디렉토리를 생성할 수 없습니다 ({e}). 경로와 권한을 확인해주세요."
    ) from e

ALLOWED_EXTENSIONS = {"pdf"}

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# LangSmith 트레이싱 (LANGCHAIN_TRACING_V2=true 설정 시 자동 활성화)
LANGSMITH_TRACING = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
