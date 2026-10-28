# 비즈니스 규칙 및 환불 정책 (Business Rules)

## 1. 환불 정책 임계값 설정 (Configuration)

모든 정책 수치는 소스 코드에 하드코딩되지 않으며, 환경변수 및 정책 객체(`PolicyConfig`)로 관리됩니다.

- `POLICY_FULL_REFUND_DAMAGE_RATIO` (기본값: 30%)
- `POLICY_PARTIAL_REFUND_DAMAGE_RATIO` (기본값: 10%)
- `POLICY_MAX_CLAIM_DAYS` (기본값: 2일 = 배송 완료 후 48시간)
- `POLICY_MIN_VISION_CONFIDENCE` (기본값: 0.70)

---

## 2. 결정론적 판정 기준표

| 조건 | 판정 (Decision) | 사유 코드 (Reason Code) | 처리 방식 |
|------|-----------------|-------------------------|-----------|
| 배송 완료 이전 주문 | `REJECT` | `ORDER_NOT_DELIVERED` | 배송 완료 후 재접수 안내 |
| 배송 완료 후 48시간 초과 | `REJECT` | `EXPIRED_WINDOW` | 신선식품 보상 기한 초과 안내 |
| 사진 품질 불량 (`blurry`, `too_dark`) | `RETAKE_IMAGE` | `POOR_IMAGE_QUALITY` | 밝은 곳 재촬영 가이드 전송 |
| 판독 신뢰도 < 0.70 또는 결함 식별 불가(`unclear`) | `MANUAL_REVIEW` | `CONFIDENCE_TOO_LOW` / `UNCLEAR_DEFECT` | 관리자 수동 검토 큐 이관 |
| 동일 이미지 해시 중복 제출 | `MANUAL_REVIEW` | `SUSPICIOUS_CLAIM` | 사기 의심 격리 및 담당자 확인 |
| 정상 상품 관측 (손상률 0%) | `REJECT` | `NORMAL_PRODUCT` | 손상 부위 추가 접수 안내 |
| 경미한 외관 흠집 (손상률 < 10%) | `REJECT` | `COSMETIC_DEFECT` | 농산물 유통 허용 오차 안내 |
| 손상률 >= 30% | `FULL_REFUND` | `SEVERE_DAMAGE` | 100% 자동 전액 환불 접수 |
| 10% <= 손상률 < 30% | `PARTIAL_REFUND` | `PARTIAL_DAMAGE` | 손상률 비례 부분 환불 접수 |

---

## 3. 이상 징후 (Fraud Detection) 방어 로직

- **Perceptual / SHA-256 해시 검사**: 과거 클레임에 제출된 동일 이미지 해시와 일치하는 경우 자동 승인을 즉시 중단하고 `SUSPICIOUS_CLAIM`으로 전환.
- **빈도 제한**: 동일 고객이 최근 30일 내 3회 이상 클레임을 반복 접수하는 경우 관리자 수동 검토 필수 지정.
- **안전 원칙**: 시스템은 고객을 사기범으로 단정하거나 임의로 차단하지 않고, 신중하게 관리자 검토 큐(`MANUAL_REVIEW`)로 이관합니다.
