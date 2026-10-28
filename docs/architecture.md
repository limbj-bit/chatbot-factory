# 시스템 아키텍처 (System Architecture)

## 1. 개요 및 설계 철학

본 플랫폼은 **신선식품 이커머스용 AI CS + 사진 기반 손상 판독 + 반품/환불 자동화 SaaS**입니다.
Martin Fowler의 Domain-Driven Design(DDD) 및 Robert C. Martin(Uncle Bob)의 Clean Architecture 원칙에 따라 설계되었습니다.

### ⚠️ 절대 불변 원칙: AI와 비즈니스 의사결정의 분리

```
[고객 사진 업로드]
        ↓
[Vision AI Provider]
        ↓ (순수 관측 데이터: Defect Type, 손상비율, 품질지표)
[Deterministic Rule Engine]
        ↓ (결정: FULL_REFUND / PARTIAL_REFUND / RETAKE_IMAGE / MANUAL_REVIEW)
[E-Commerce Channel Adapter (Cafe24 등)]
        ↓ (멱등성 보장 상태 변경: Idempotency Key)
[LLM Communication Layer]
        ↓ (자연어 스트리밍 SSE 브리핑)
[고객 화면 (Widget)]
```

- **Vision AI**: 물리적 손상 관측(Observation)만 수행하며, 환불 여부를 직접 결정하지 않습니다.
- **Rule Engine**: 100% 결정론적(Deterministic) 도메인 규칙으로 최종 의사결정을 내립니다.
- **Channel Adapter**: 멱등성 키(`claim_id + operation_id`)를 기반으로 안전하게 반품/환불 요청을 실행합니다.
- **LLM**: 판정 결과를 친절한 대화형 자연어로 고객에게 설명합니다.

---

## 2. 계층 구조 (Clean Architecture)

```
app/
├── api/             # Presentation Layer: FastAPI 라우터, SSE 스트리밍, 에러 핸들링
├── application/     # Application Layer: 유스케이스 오케스트레이션, 멱등성 제어
├── domain/          # Domain Layer: 엔티티, 값 객체, 순수 정책 규칙 엔진, 도메인 포트
├── infrastructure/  # Infrastructure Layer: AI 라우터, Cafe24 어댑터, RAG, DB, Redis
├── schemas/         # Pydantic v2 DTOs 및 요청/응답 스키마
└── core/            # 설정, 로깅(Correlation ID), 보안(Magic Bytes, API Key)
```

---

## 3. 다중 AI Provider 라우터 및 서킷 브레이커

- **태스크 기반 최적화**:
  - 일반 대화 및 CS: `Groq` (초저지연 Llama-3/Mixtral)
  - 복합 추론 및 의도 분석: `NVIDIA NIM`
  - 과일 이미지 손상 분석: `Google Gemini 1.5 Flash Vision`
- **429 Rate Limit 및 장애 자동 극복**:
  - 429 감지 시 즉각 Cooldown(30초) 설정 및 다음 Provider로 자동 Fallback.
  - 지수 백오프(Exponential Backoff) 기반 Bounded Retry (최대 2회).
  - 모든 Provider 실패 시: 친절한 고객센터 안내 메시지 + 구조화 로그 Alert.

---

## 4. RAG 및 비용 최적화 계층

비용 절감 원칙: `CACHE → RULE/FAQ → RAG → LLM`
- 배송비, 운영시간, 무통장 입금 계좌, 반품 기본 규정 등은 LLM 호출 없이 0원으로 즉시 응답.
- 상품별 보관법 및 섭취 가이드는 RAG 검색을 통해 엄격한 출처 메타데이터와 함께 답변 생성 (환각 원천 차단).

---

## 5. 멱등성 및 금전/상태 안전성

- 모든 반품 및 환불 작업에는 `f"claim:{claim_id}:refund:{operation_id}"` 고유 멱등키가 부여됩니다.
- 외부 API 호출 지연 또는 타임아웃 발생 시, 임의로 재시도하거나 성공으로 간주하지 않고 `UNKNOWN_EXTERNAL_STATE`로 마킹하여 관리자 검토 큐로 이관합니다.
