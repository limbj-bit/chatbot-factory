# 신선식품 AI 고객센터 & 사진 클레임 자동화 SaaS

신선식품 이커머스를 위한 **AI CS + 사진 기반 손상 판독 + 반품/환불 자동화 플랫폼**입니다.
Martin Fowler의 Domain-Driven Design(DDD)과 Robert C. Martin의 Clean Architecture 원칙에 따라 구축되었습니다.

---

## 🌟 핵심 설계 원칙: AI와 비즈니스 의사결정의 분리

AI가 직접 환불 승인 여부를 결정하지 않습니다.

1. **Vision AI**: 사진에서 관찰되는 물리적 손상(Defect Type, 손상 면적 비율, 신뢰도, 사진 품질)을 구조화된 JSON 데이터로 관측·보고.
2. **Deterministic Rule Engine**: 사전에 정의된 쇼핑몰 정책(손상률 임계값, 배송 경과 시간, 고객 클레임 이력)에 따라 100% 결정론적으로 환불 여부 판정.
3. **E-Commerce Channel Adapter**: Cafe24 등 쇼핑몰 API를 통해 멱등성(Idempotency)을 보장하며 안전하게 반품 접수 및 환불 실행.
4. **LLM**: 판정 결과를 친절한 대화형 자연어(SSE 스트리밍)로 고객에게 설명.

---

## 🛠️ 기술 스택

- **Core Backend**: Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2.0 (Async), aiosqlite / asyncpg, Redis, httpx, pytest
- **AI Providers**: Groq (초저지연 CS), NVIDIA NIM (복합 추론), Google Gemini 1.5 Flash (Vision 손상 계측), Multi-Provider Router with 429 Fallback
- **E-Commerce**: Cafe24 Open API Adapter (향후 네이버 스마트스토어, 쿠팡 등으로 확장 가능한 Hexagonal Port 구조)
- **Frontend**: 독립형 임베더블 JavaScript 위젯 (`chatbot-widget.js`) + SSE 실시간 스트리밍
- **Infrastructure**: Docker, docker-compose, Structured JSON Logging, Correlation ID

---

## 🚀 빠른 시작 (Local Setup)

### 1. 가상환경 및 의존성 설치 (`uv` 권장)
```bash
# 가상환경 생성 및 패키지 설치
uv venv
uv pip install -e ".[dev]" greenlet
```

### 2. 환경변수 설정
```bash
cp .env.example .env
```
기본적으로 `.env`에는 `MOCK_AI=true`와 `MOCK_CAFE24=true`가 설정되어 있어, **외부 유료 API 키 없이도 전체 시스템과 테스트가 100% 정상 작동**합니다.

### 3. 서버 실행
```bash
uvicorn app.main:app --reload --port 8000
```
- API 문서 (Swagger): http://localhost:8000/docs
- 위젯 데모 페이지: http://localhost:8000/static/index.html
- 헬스 체크: http://localhost:8000/health

---

## 🧪 테스트 실행 (Test Suite)

총 46개의 테스트(Unit, Integration, E2E)가 작성되어 있으며, 손상률 경계값(0%, 9%, 10%, 29%, 30%, 31%), Provider 429 서킷 브레이커, 중복 환불 멱등성, 사진 매직 바이트 검증을 모두 커버합니다.

```bash
# 전체 테스트 실행
pytest -xvs
```

---

## 🐳 Docker 실행 (Docker Compose)

PostgreSQL 및 Redis와 함께 프로덕션 환경 컨테이너 스택을 구동합니다:

```bash
docker compose -f docker/docker-compose.yml up --build -d
```

---

## 🔌 실제 API 연동 방법 (Production Mode)

실제 서비스를 연동하려면 `.env` 파일의 플래그를 변경하고 키를 입력합니다:

```env
# 모의 모드 해제
MOCK_AI=false
MOCK_CAFE24=false

# AI Provider 키
GROQ_API_KEY=gsk_your_groq_api_key
NVIDIA_API_KEY=nvapi_your_nvidia_api_key
GEMINI_API_KEY=AIzaSy_your_gemini_api_key

# 카페24 오픈 API 연동
CAFE24_MALL_ID=your_mall_id
CAFE24_CLIENT_ID=your_client_id
CAFE24_CLIENT_SECRET=your_client_secret
CAFE24_ACCESS_TOKEN=your_oauth_access_token

# 데이터베이스 (PostgreSQL)
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/fresh_claims
REDIS_URL=redis://localhost:6379/0
```

---

## 🛡️ 보안 및 멱등성 보장 (Security & Idempotency)

1. **파일 업로드 매직 바이트 검증**: 파일 확장자 위조를 방지하기 위해 JPEG(`0xFFD8FF`), PNG(`0x89PNG`), WebP(`RIFF...WEBP`) 바이너리 헤더를 직접 검증합니다.
2. **중복 환불 방지 (Idempotency)**: `claim:{claim_id}:refund:{operation_id}` 멱등키를 발급하여 동일 요청이 여러 번 호출되어도 중복 출금되지 않습니다.
3. **외부 API 타임아웃 보호**: 카페24 API 타임아웃 시 임의로 성공 간주하지 않고 `UNKNOWN_EXTERNAL_STATE`로 마킹하여 관리자 검토 큐로 격리합니다.
4. **관리자 엔드포인트 보호**: `GET /api/admin/claims`, `POST /api/admin/claims/{id}/approve`는 `X-Admin-Key` 헤더를 통해 인가됩니다.
