# 사진 판독(클레임 비전) 경쟁사 벤치마킹 & 고도화 보고서 (2026-11)

> 대상: 챗봇공장 `fresh_food` wedge(사진 클레임 자동화) + `beauty` expansion(성분 상담/카드 전환)
> 방법: 우리 코드/라이브 구조 분석 + Gorgias/Intercom/Channel Talk 공개 문서 + 이미지 포렌식/사기 방어 자료
> 증거 구분: **관측(Observed)** / **추론(Inferred)** / **권고(Recommendation)**

---

## 0. 요약 (Executive Summary)

1. **우리의 강점은 "관측과 결정의 분리"다.** 비전 모델은 물리 관측(defect_type, damage_ratio, confidence, image_quality)만 보고하고, 환불 결정은 정책 엔진(`RefundPolicyEngine`)이 담당한다. 경쟁사(Gorgias/Intercom)는 LLM이 Guidance/Task 지시를 읽고 직접 환불 가능성을 판단한다. 우리 방식은 **재현 가능성·감사 가능성·업종별 확장성**에서 우위다.
2. **경쟁사는 "설정 한 줄"로 비전을 켠다.** Gorgias는 Guidance 텍스트 한 문장, Intercom은 Task 지시로 비전을 제어한다. 우리는 업종별 프롬프트 + 정책 슬라이더(50~95%) + vision 정밀도 설정을 제공하지만, **Guidance 수준의 "자연어 정책 한 문장" 인터페이스**가 없다. 셀프서비스 온보딩에서 경쟁사보다 마찰이 크다.
3. **사기·조작 방어가 다음 전쟁터다.** 2026년 기준 보험/커머스에서 AI 생성 손상 사진이 실존 위협으로 부상했다(CheckFile.ai, Sorquil). 우리 중복 해시는 **완전 동일 파일**만 잡는다. **AI 생성/편집 사진 탐지, EXIF/메타데이터, 다각도 사진, 역이미지 검색**이 필요하다.
4. **다중 이미지·영상·증거 묶음**이 부족하다. Intercom은 최대 3장 이미지를 답변에 포함하고, Gorgias는 chat/email 이미지를 읽는다. 우리는 단일 `is_primary` 이미지 중심이다. 식품 클레임에서 **"전체 상품 + 클로즈업 + 포장" 3장 세트**가 표준이어야 한다.
5. **모바일/HEIC/압축/업로드 UX**는 경쟁사가 먼저 해결했다. Intercom은 HEIC를 읽는다. 우리는 `validate_image_file`로 MIME 매직 바이트를 검사하지만, HEIC/HEIF 지원과 클라이언트 측 압축/리사이즈가 없다.
6. **권고**: "잘하는 것을 더 잘하기" 위해 (a) 다중 이미지+증거 묶음, (b) AI 생성/편집 사진 방어, (c) 신뢰도 캘리브레이션+골든셋 평가, (d) Guidance 스타일 자연어 정책, (e) 인간 검토 UI/SLA, (f) 모바일 업로드 최적화를 P0~P2로 추진한다.

---

## 1. 우리 현재 역량 (Observed, 코드 기반)

### 1.1 비전 관측 스키마 (`vision_prompts.py`)
- 단일 JSON 스키마: `defect_type` (32 코드), `affected_items`, `damage_ratio_estimate(0-100)`, `confidence(0-1)`, `visible_evidence[]`, `image_quality(acceptable|blurry|too_dark|occluded|invalid)`.
- 업종별 focus 11종(fresh_food, raw_materials, beauty, fashion, electronics, interior, pet, baby, sports, medical, restaurant). fresh_food는 곰팡이·부패·눌림·파손·변색·과숙 + 손상 비율 추정.
- 규칙: "환불/비즈니스 결정 금지, 물리 관측만 보고."

### 1.2 클레임 파이프라인 (`claim_service.py`)
- MIME 매직 바이트 검증(`validate_image_file`), 경로 탐색 방어(basename + `UPLOAD_DIR` 루트 검사).
- 중복 해시(`compute_sha256`)로 동일 파일 재사용 탐지(사기 신호).
- 업종별 vision 프롬프트 자동 선택(`_industry_for_mall`).
- 정책 엔진(`RefundPolicyEngine`)이 관측값 + 주문/고객 이력 + 48시간 규칙을 결합해 결정.
- 식품안전(곰팡이/이물/식중독 의심)은 AI 단독 판정 금지, 사람 인계 원칙(보고서 3.7).
- Vision 정밀도 슬라이더 50~95%(기본 70%), 업종별 vision 프롬프트, OpenRouter vision 백업.

### 1.3 정책 설정 (`_policy_engine_for_mall`)
- 매장별 `claim_policy`: `min_vision_confidence`, `max_claim_days`, `full_refund_damage_ratio`, `partial_refund_damage_ratio`.
- 슬라이더 범위 50~95%, 기본 70%. 클레임 정책은 매장 "고급 설정"에서 override 가능.

### 1.4 강점 요약
- 관측/결정 분리 → 감사·재현 가능.
- 업종 11종 focus → 신선식품에 최적화.
- 정책이 코드가 아니라 데이터(매장 설정) → B2B 셀프서비스.
- 중복 해시 → 단순 재업로드 사기 차단.
- 이미지 품질 게이팅 → blurry/dark/occluded 시 retake 요구.

---

## 2. 경쟁사 비전 역량 (Observed)

### 2.1 Gorgias AI Agent — Vision (2026)
- **기능**: chat/email에서 고객이 보낸 이미지를 읽고 환불/반품 적격성을 판단. 에이전트가 사진을 열어볼 필요 없음(2026-07-24 Chat 지원 추가).
- **제어 방식**: Guidance 텍스트 한 문장(예: "이미지가 명확히 손상된 제품을 보여주면 정책에 따라 환불/교환"). 설정 패널에 위치, SOP 라이브러리와 분리.
- **지원 포맷**: PNG, JPEG, WEBP, non-animated GIF.
- **액션**: Shopify 주문 환불/취소/편집을 대화 중 자동 실행. $0.90~$1.00 per automated interaction + 티켓 요금.
- **강점**: 채널 통합(email/chat/SMS/Instagram/Facebook/WhatsApp), Shopify 네이티브 액션, 빠른 온보딩.
- **약점(우리 관점)**: Guidance가 "shadow SOP" — 짧은 문장에 정책 전체가 의존, 달러 임계값/샘플링 감사가 없으면 오판. 식품 특화 defect vocabulary나 손상 비율 추정 없음. (출처: Reccord SOP 2026-08-15)

### 2.2 Intercom Fin Vision (2026)
- **기능**: chat/email에서 스크린샷·사진·문서를 분석. 별도 설정/비용 없음. HEIC 지원(iPhone 기본 포맷).
- **유스케이스**: damaged/incorrect product 사진으로 반품·환불 적격성 평가(Task 지시 기반), 패키징 손상, 누락 부품, 송장/주문번호 추출.
- **개인정보**: 신용카드 번호/CVV/신분증 등 민감정보 추출 금지 프롬프트.
- **답변에 이미지 포함**: 최대 3장 이미지/GIF를 답변에 첨부(2026-01-22).
- **강점**: HEIC, 멀티 이미지 답변, 비용 0, 80+ 언어.
- **약점**: Task 지시 품질에 의존, defect vocabulary/손상 비율 정량화 없음, 식품 특화 없음.

### 2.3 Channel Talk ALF (한국, 2026)
- **기능**: Task 기반 주문 취소/환불 자동화(JavaScript 실행), 32개 언어, $0.5 per chat participation.
- **이미지**: 썸네일 + EXIF orientation 지원(메타데이터 보존). 그러나 **이미지 판독 기반 클레임 판정**은 공개 문서에 없음 — 주문 조회/환불 실행 중심.
- **강점**: 한국 커머스 생태계(Cafe24? Naver? 카카오), 저비용, 빠른 셋업.
- **약점**: 식품 클레임/비전 판정이 공개적으로 확인되지 않음 → 우리가 wedge로 파고들 수 있는 공백.

### 2.4 Zendesk / Tidio (요약)
- Zendesk AI: 이미지 이해는 일반 LLM 수준, 반품/환불은 매크로/Flow. 식품 특화 없음.
- Tidio: Lyro AI, 이미지 이해 제한적, 주문 상태 조회 중심.
- **공통 약점**: 신선식품 defect vocabulary, 손상 비율, 48시간 정책, 부분환불 티어 없음.

### 2.5 이미지 사기/포렌식 (2026)
- **Sorquil**: Shopify 환불 사진의 AI 편집 탐지(메타데이터, error level, 노이즈, 모델 스코어, 히트맵). "환불 전에 사진을 먼저 본다."
- **CheckFile.ai**: AI 생성 손상 사진 위협. 99% 보험사가 조작/ AI 변조 문서 경험. AI 생성 사진은 원본이 없어 클론스탬프/ELA가 무력.
- **MyTools 사례**: 48시간 클레임 창, 사진에 빨간 원으로 손상 표시 → 심사자 가독성.
- **시사점**: 2026년 환불 사진 사기가 **편집(Edited real photo)** 에서 **생성(Synthetic photo)** 으로 이동 중. 우리 중복 해시는 이 두 유형을 거의 잡지 못한다.

---

## 3. 역량 비교 매트릭스

| 역량 | 우리 | Gorgias | Intercom Fin | Channel ALF |
|---|---|---|---|---|
| 비전 내장 | ✅ (nvidia/openrouter 백업) | ✅ | ✅ | ❓ (미확인) |
| 업종별 defect vocabulary | ✅ 11종 | ❌ (Guidance 자유) | ❌ (Task 지시) | ❌ |
| 손상 비율 정량화 | ✅ 0-100% | ❌ | ❌ | ❌ |
| 관측/결정 분리 | ✅ | ❌ (LLM 직접) | ❌ | ❌ |
| 정책 슬라이더 (50-95%) | ✅ | ❌ (Guidance 텍스트) | ❌ | ❌ |
| 매장별 override | ✅ | ✅ (Guidance) | ✅ (Task) | ❌ |
| 다중 이미지 | ❌ (단일 primary) | ✅ (chat/email) | ✅ (최대 3장 답변) | ❌ |
| HEIC 지원 | ❌ | ❌ | ✅ | ❓ |
| EXIF/메타데이터 | ❌ | ❌ | ❌ | ✅ (orientation) |
| AI 생성/편집 사진 탐지 | ❌ (해시만) | ❌ | ❌ | ❌ |
| 인간 검토 UI/SLA | ⚠️ (알림만) | ✅ | ✅ | ✅ |
| 자동 환불 실행 | ⚠️ (서비스 존재) | ✅ (Shopify) | ✅ | ✅ (Task) |
| 비용 모델 | LLM 비용 (우리 부담) | $0.90-1.00/건 + 티켓 | resolution 과금 | $0.5/건 |

---

## 4. 고도화 기회 (잘하는 것을 더 잘하기)

### P0 — wedge(신선식품) 직결, 1~2주

1. **다중 이미지 증거 묶음 (3장 세트)**
   - `ClaimImageModel`에 `role(primary|overview|closeup|packaging)` 추가.
   - 업로드 UI: "전체 상품 / 손상 부위 클로즈업 / 포장재" 3장 가이드.
   - 비전 관측을 이미지별로 수집 후 정책 엔진에 `max_damage_ratio`, `min_confidence` 집계.
   - 근거: MyTools 48시간 클레임 사례 — "사진에 빨간 원으로 손상 표시"가 심사자 가독성을 높임. 우리는 `visible_evidence`를 구조화해 오버레이로 표시 가능.

2. **AI 생성/편집 사진 방어 (최소 viable)**
   - EXIF 존재 여부, 카메라 모델, 촬영 시각, GPS 등 메타데이터 추출·저장.
   - 역이미지 검색( perceptual hash, pHash )으로 동일 이미지 재사용 탐지(현재 SHA-256은 리사이즈/재압축에 무력).
   - "메타데이터 없음 + 고해상도 + 손상 영역만 선명" 같은 휴리스틱으로 `image_quality=suspicious` 추가.
   - AI 생성 탐지 API 연동은 P1(비용/정확도 검증 후).

3. **신뢰도 캘리브레이션 + 골든셋 평가**
   - fresh_food 18장(정상/경미/심각) 골든셋으로 precision/recall/F1 측정.
   - vision 정밀도 슬라이더와 실제 정확도의 상관관계 측정 → 기본값 70% 재검증.
   - 모델별(NVIDIA/OpenRouter) 정확도 비교 → 백업 라우팅 우선순위 근거.

4. **Guidance 스타일 자연어 정책**
   - 매장 "고급 설정"에 자유 텍스트 정책 입력란 추가 → LLM이 정책을 읽고 비전 관측과 결합.
   - 단, 우리 원칙 유지: LLM은 정책 해석만, 환불 결정은 엔진. "관측+정책해석 → 엔진 결정" 3단 구조.

### P1 — 확장/운영, 2~4주

5. **인간 검토 UI + SLA**
   - `ClaimStatus`에 `PENDING_HUMAN_REVIEW`, `APPROVED`, `REJECTED` 상태 + 대시보드 큐.
   - 식품안전(곰팡이/이물/식중독) 자동 에스컬레이션 + 24h SLA.
   - Gorgias/Intercom처럼 "AI 추천 + 인간 승인" 하이브리드.

6. **모바일 업로드 최적화**
   - 클라이언트 측 리사이즈/압축(긴 변 1600px, JPEG q=0.85) → 업로드 속도/비용.
   - HEIC → JPEG 변환(서버 또는 클라이언트).
   - 업로드 진행률 + 재촬영 가이드(손상 부위 클로즈업).

7. **부분 손상 자동 환불 티어 정교화**
   - 현재: 전액 30% / 부분 10% / 접수 2일.
   - damage_ratio 기반 **연속 환불율**(예: 10% 손상 → 10%, 50% → 50%) + 상한/하한.
   - "부분 사용 가능" 시나리오(과일 1개만 손상) → 해당 SKU만 환불.

8. **감사 로그/내보내기**
   - 클레임별 관측 JSON + 정책 결정 + 이미지 해시 + 타임스탬프를 CSV/PDF로 내보내기.
   - 고객사가 ROI 증명(환불 절감, 처리 시간) 가능 → SaaS 가치.

### P2 — 장기, 1~2개월

9. **영상 클레임 지원** (10초 이내 짧은 영상 → 프레임 샘플링 → 비전).
10. **운송사 연동**: 배송 중 파손 클레임 → 운송사 보험 자동 청구.
11. **다국어 클레임**: 32개 언어(Intercom 수준) — fresh_food wedge는 한국 우선이지만 export 시 필요.
12. **A/B 평가 인프라**: 모델/프롬프트 변경 시 골든셋 자동 회귀.

---

## 5. KPI (사진 판독 전용)

| 지표 | 현재 (Inferred) | 목표 (3개월) |
|---|---|---|
| 비전 정확도 (defect_type) | 미측정 | ≥ 90% (골든셋) |
| damage_ratio 오차 | 미측정 | ±10%p |
| confidence 캘리브레이션 (ECE) | 미측정 | < 0.1 |
| 이미지 품질 reject율 | 미측정 | < 15% (retake 안내) |
| 자동 처리율 (사람 개입 없음) | 미측정 | ≥ 70% (신선식품) |
| 오판율 (고객 이의) | 미측정 | < 5% |
| 평균 처리 시간 | 미측정 | < 30초 (업로드→결정) |
| 사기 탐지율 (중복/조작) | 해시만 | ≥ 80% (휴리스틱) |

---

## 6. 리스크 & 가드레일

- **식품안전**: 곰팡이/이물/식중독 의심은 AI 단독 판정 금지, 사람 인계. 이 원칙은 고도화에서도 유지.
- **과잉 자동화**: confidence < 70% 또는 image_quality != acceptable → 자동 retake/인계.
- **사기**: AI 생성 사진 위협 → 다중 이미지 + 메타데이터 + 휴리스틱 + (P2) 전문 탐지 API.
- **개인정보**: Intercom처럼 신용카드/CVV/신분증 추출 금지 프롬프트 유지. 업로드 이미지의 EXIF GPS는 저장 전 제거(개인정보 보호).
- **법적**: 부분환불 자동 실행은 전자상거래법/소비자 보호법 검토 필요. 한국 7일 청약철회와 48시간 품질보상 구분 유지.

---

## 7. 의사결정 요청

1. **다중 이미지 + AI 사기 방어를 P0로 승인**할 것인가? (2주, wedge 직결)
2. **Guidance 스타일 자연어 정책**을 "관측+해석+결정 3단"으로 구현할 것인가?
3. **골든셋 18장**을 실제로 촬영/수집할 책임자와 일정은?
4. **인간 검토 UI**를 P1로 미룰 것인가, 식품안전 때문에 P0로 당길 것인가?

---

## 8. 참고 자료 (Observed)

- Gorgias Help Center: "AI Agent explained" (Vision, 2026-09-08), "20/20 Vision: AI Agent can now read images sent in Chat" (2026-07-24), "Automate Returns and Refunds" use case.
- Reccord SOP: "Gorgias AI Agent Vision: The Refund SOP Gap It Just Created" (2026-08-15) — Guidance가 shadow SOP.
- Intercom Help: "How Fin Vision understands images" (2026-05-14) — HEIC, Task 지시, 개인정보 가드레일, 최대 3장 이미지 답변.
- Channel Talk: Task 문서, 가격 페이지 (ALF $0.5/chat, 32언어, EXIF orientation).
- Sorquil: "A Buyer Sent a Fake Damage Photo? How to Ask for More Evidence" (2026-09-24).
- CheckFile.ai: "AI-Generated Damage Photos: The New Refund Fraud Threat" (2026-09-13) — 99% 보험사 조작 경험.
- MyTools: "Forty-Eight Hours to Prove the Couch Arrived Damaged" (2026-06-15) — 48시간 창, 빨간 원 표시.
- 우리 코드: `app/infrastructure/ai/vision_prompts.py`, `app/application/claim_service.py`, `app/domain/policies/refund_policy.py`.
- REA: 라이브 Render 로딩 페이지 캡처 시도(콜드스타트로 앱 DOM 미수신) — `ev_02b0b2a734ae8d9d4a4a5cb62a1c36e69fca48dfd691cab46428e0e47c7c8dba`.
