"""Industry-aware vision prompt builder for claim image diagnosis.

The vision model is told (a) the shared output schema and (b) industry-specific
guidance on what counts as a defect. This keeps one deterministic JSON schema
while letting the physical-observation focus differ per industry (fresh food vs
beauty vs electronics, etc.).

Zero dependencies on providers/frameworks — pure string building.
"""

from __future__ import annotations

# Defect vocabulary is industry-neutral and shared across the schema. Providers
# must only return one of these codes.
DEFECT_CODES = [
    "mold",            # 곰팡이/변질 (식품)
    "rot",             # 썩음/부패 (식품)
    "bruise",          # 눌림/상함 (식품·과일)
    "crush_damage",    # 파손/눌림 (전자·리빙)
    "crack",           # 균열/깨짐 (전자·리빙·유리)
    "shattered",       # 완전 파손/파괴
    "scratch",         # 표면 스크래치 (전자·패션·리빙)
    "stain",           # 얼룩/오염 (패션·리빙)
    "leak",            # 누수/누유 (화장품·가전·용기)
    "missing_parts",   # 부품/구성품 누락
    "malfunction",     # 작동 불량 (전자·가전)
    "wrong_item",      # 오배송/다른 상품
    "size_mismatch",   # 사이즈/치수 불일치 (패션)
    "cosmetic_defect", # 경미 외관 흠집 (허용 범위)
    "normal",          # 이상 없음
    "unclear",         # 판독 불가
]

IMAGE_QUALITIES = ["acceptable", "blurry", "too_dark", "occluded", "invalid"]

# Per-industry physical-observation guidance. Only affects WHAT to look for;
# the output schema and refund logic stay identical across industries.
_INDUSTRY_FOCUS = {
    "fresh_food": (
        "This is a FRESH FOOD / agricultural product claim. Look for mold, rot, "
        "bruising, crushing, discoloration, sogginess, or spoilage. Estimate the "
        "percentage of the edible product that is damaged or spoiled."
    ),
    "raw_materials": (
        "This is a RAW MATERIAL / ingredient claim. Look for contamination, mold, "
        "moisture damage, foreign material, or spoilage. Estimate damaged share."
    ),
    "beauty": (
        "This is a BEAUTY / cosmetics claim. Look for leakage/spillage from the "
        "container, a broken or cracked pump/nozzle/lid, seal damage, contamination "
        "(color/odor/texture change), packaging cracks, or a malfunctioning "
        "applicator. Estimate the share of the product or package that is affected."
    ),
    "fashion": (
        "This is a FASHION / apparel claim. Look for stains, tears, holes, loose or "
        "missing seams/buttons/zippers, print cracking/peeling, color dye defects, "
        "wrong size label, or wrong item. Estimate the affected area share."
    ),
    "electronics": (
        "This is an ELECTRONICS / device claim. Look for cracks, scratches, shattered "
        "screens or casing, dents, missing parts, liquid damage, or visible malfunction. "
        "Estimate the affected area/functional share."
    ),
    "interior_realestate": (
        "This is an INTERIOR / furnishing / home-goods claim. Look for scratches, "
        "cracks, dents, stains, broken glass/parts, assembly defects, or finish damage. "
        "Estimate the affected area share."
    ),
    "pet_supplies": (
        "This is a PET SUPPLIES claim. Look for contamination, mold, broken parts, "
        "leakage, or damage to the product. Estimate the affected share."
    ),
    "baby_kids": (
        "This is a BABY / KIDS product claim. Look for broken parts, cracks, sharp or "
        "damaged edges, stains, leakage, or safety-related defects. Estimate affected share."
    ),
    "sports_leisure": (
        "This is a SPORTS / LEISURE gear claim. Look for cracks, breaks, tears, "
        "malfunction, missing parts, or structural damage. Estimate affected share."
    ),
    "medical_clinic": (
        "This is a MEDICAL / clinic-related product claim. Look for contamination, "
        "packaging damage, leakage, or defects affecting safe use. Estimate affected share."
    ),
    "restaurant_cafe": (
        "This is a FOOD & BEVERAGE (restaurant/cafe) claim. Look for spoilage, mold, "
        "foreign material, contamination, or improper condition. Estimate damaged share."
    ),
}

_FALLBACK_FOCUS = (
    "Inspect the product image for any physical damage, defect, contamination, "
    "or anomaly. Estimate the percentage of the product that is affected."
)


def _industry_focus(industry: str | None) -> str:
    if not industry:
        return _FALLBACK_FOCUS
    return _INDUSTRY_FOCUS.get(industry.strip().lower(), _FALLBACK_FOCUS)


def build_vision_instruction(industry: str | None = None) -> str:
    """Build the full user instruction (schema + industry focus) for the vision model.

    Returns a prompt that demands a single valid JSON object and forbids any
    refund/business decisions — the model only reports physical observations.
    """
    defect_enum = " | ".join(f'"{c}"' for c in DEFECT_CODES)
    quality_enum = " | ".join(f'"{q}"' for q in IMAGE_QUALITIES)

    return (
        "Analyze this product image for physical damage or defects.\n"
        f"{_industry_focus(industry)}\n\n"
        "Respond ONLY with a valid JSON object matching this schema:\n"
        "{\n"
        f'  "defect_type": {defect_enum},\n'
        '  "affected_items": <integer>,\n'
        '  "damage_ratio_estimate": <integer 0-100>,\n'
        '  "confidence": <float 0.0-1.0>,\n'
        '  "visible_evidence": [<string>, ...],\n'
        f'  "image_quality": {quality_enum}\n'
        "}\n\n"
        "Rules:\n"
        "- defect_type must be the single best-fit code from the list.\n"
        "- damage_ratio_estimate is the percentage of the product/item that is damaged.\n"
        "- confidence is how certain you are of this observation (0.0-1.0).\n"
        "- visible_evidence lists concrete things you actually see in the image.\n"
        "- If the image is too blurry/dark/occluded to judge, set image_quality accordingly "
        "and use defect_type \"unclear\".\n"
        "- Do NOT make refund or business decisions. Only report physical observations."
    )
