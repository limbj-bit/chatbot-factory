# Fresh Food Claim AI SaaS (신선식품 AI CS & 클레임 자동화 플랫폼)

신선식품 이커머스용 AI CS + 사진 기반 손상 판독 + 반품/환불 자동화 플랫폼.

## 핵심 아키텍처 원칙
1. **Vision AI**: 사진에서 관찰되는 물리적 손상(Defect Type, 손상비율, 품질)을 구조화된 데이터(JSON)로 관측.
2. **Rule Engine**: 사전에 정의된 쇼핑몰 정책에 따라 결정론적(Deterministic)으로 환불/반품 판정.
3. **Channel Adapter**: Cafe24 등 외부 쇼핑몰 API를 통해 멱등성(Idempotency) 있게 상태 변경 실행.
4. **LLM**: 판정 결과를 고객에게 친절한 자연어(SSE 스트리밍)로 안내.
