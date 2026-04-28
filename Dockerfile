FROM python:3.11-slim

WORKDIR /app

# 시스템 의존성 설치
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성 설치
COPY Pipfile Pipfile.lock ./
RUN pip install pipenv && \
    pipenv install --deploy --ignore-pipfile && \
    pipenv run pip install slowapi

# 애플리케이션 코드 복사
COPY . .

# 업로드 디렉토리 생성
RUN mkdir -p app/uploads

# 포트 노출
EXPOSE 7860

# 환경 변수 설정
ENV PYTHONUNBUFFERED=1

# 서버 실행
CMD ["pipenv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]

