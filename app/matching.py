"""Explainable candidate ranking for LostLink.

The lightweight baseline works without external APIs. Optional Sentence
Transformers and CLIP models can be enabled for semantic text and visual
similarity. The engine never treats a score as proof of ownership.
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from PIL import Image

SYNONYMS = {
    "backpack": "bag", "rucksack": "bag", "purse": "wallet",
    "handbag": "bag", "satchel": "bag", "flask": "bottle",
    "thermos": "bottle", "earbud": "earbuds", "airpod": "earbuds",
    "headphone": "headphones", "spectacle": "glasses",
    "spectacles": "glasses", "eyeglass": "glasses", "eyeglasses": "glasses",
    "identity": "id", "identification": "id", "cardholder": "wallet",
    "navy": "blue", "bluish": "blue", "grey": "gray", "silver": "gray",
}
STOP_WORDS = {
    "a", "an", "the", "and", "or", "with", "of", "for", "to", "at",
    "in", "on", "near", "my", "i", "it", "is", "was", "were", "has",
    "have", "had", "this", "that", "item", "found", "lost", "around",
}


def tokens(text: str) -> list[str]:
    values = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [SYNONYMS.get(x, x) for x in values if x not in STOP_WORDS]


def lexical_similarity(left: str, right: str) -> float:
    """A deterministic no-network baseline, not a learned semantic model."""
    a, b = tokens(left), tokens(right)
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    jaccard = len(sa & sb) / max(1, len(sa | sb))
    sequence = SequenceMatcher(None, " ".join(a), " ".join(b)).ratio()
    detail_terms = {"black", "blue", "red", "green", "white", "gray",
                    "gold", "scratch", "sticker", "zipper", "crack",
                    "stain", "stripe", "logo", "pocket", "case"}
    details = (sa & sb) & detail_terms
    detail_overlap = len(details) / max(1, len((sa | sb) & detail_terms))
    return min(1.0, 0.55 * jaccard + 0.30 * sequence + 0.15 * detail_overlap)


def _parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def _text_value(report: dict[str, Any]) -> str:
    # Explicit public characteristics contribute to matching without reusing private claim evidence.
    return " ".join(
        str(report.get(k) or "")
        for k in ("title", "description", "brand", "primary_color", "visible_features", "category")
    )


def _location_score(lost: dict[str, Any], found: dict[str, Any]) -> float | None:
    lb, fb = (lost.get("location_block") or "").strip().lower(), (found.get("location_block") or "").strip().lower()
    lf, ff = (lost.get("location_floor") or "").strip().lower(), (found.get("location_floor") or "").strip().lower()
    lr, fr = (lost.get("location_room") or "").strip().lower(), (found.get("location_room") or "").strip().lower()
    la, fa = (lost.get("location_area") or "").strip().lower(), (found.get("location_area") or "").strip().lower()
    if not any((lb, lf, lr, la)) or not any((fb, ff, fr, fa)):
        return None
    if lr and fr and lr == fr and (not lb or not fb or lb == fb):
        return 1.0
    if lb and fb and lb == fb:
        if lf and ff and lf == ff:
            return 0.88
        return 0.75
    if la and fa and la == fa:
        return 0.8
    if lb and fb and lb != fb:
        return 0.12
    return 0.35


def _time_score(lost: dict[str, Any], found: dict[str, Any]) -> float | None:
    ld, fd = _parse_date(lost.get("occurred_at")), _parse_date(found.get("occurred_at"))
    if not ld or not fd:
        return None
    days = abs((ld - fd).total_seconds()) / 86400
    if days <= 1:
        return 1.0
    if days <= 3:
        return 0.88
    if days <= 7:
        return 0.72
    if days <= 14:
        return 0.55
    if days <= 30:
        return 0.32
    if days <= 60:
        return 0.12
    return 0.0


class MatchingEngine:
    def __init__(self) -> None:
        self._text_model = None
        self._text_attempted = False
        self._clip_model = None
        self._clip_processor = None
        self._clip_attempted = False
        self.semantic_enabled = os.getenv("USE_SEMANTIC_MODEL", "false").lower() == "true"
        self.clip_enabled = os.getenv("USE_CLIP_MODEL", "false").lower() == "true"

    def _load_text_model(self):
        if self._text_attempted:
            return self._text_model
        self._text_attempted = True
        if not self.semantic_enabled:
            return None
        try:
            from sentence_transformers import SentenceTransformer
            self._text_model = SentenceTransformer(
                os.getenv("SEMANTIC_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
            )
        except Exception:
            self._text_model = None
        return self._text_model

    def text_similarity(self, left: str, right: str) -> tuple[float, str]:
        model = self._load_text_model()
        if model is not None:
            try:
                vectors = model.encode([left, right], normalize_embeddings=True)
                cosine = float((vectors[0] * vectors[1]).sum())
                return max(0.0, min(1.0, cosine)), "sentence_embeddings"
            except Exception:
                pass
        return lexical_similarity(left, right), "lexical_baseline"

    def _load_clip(self):
        if self._clip_attempted:
            return self._clip_model, self._clip_processor
        self._clip_attempted = True
        if not self.clip_enabled:
            return None, None
        try:
            from transformers import CLIPModel, CLIPProcessor
            model_name = os.getenv("CLIP_MODEL", "openai/clip-vit-base-patch32")
            self._clip_processor = CLIPProcessor.from_pretrained(model_name)
            self._clip_model = CLIPModel.from_pretrained(model_name)
            self._clip_model.eval()
        except Exception:
            self._clip_model = None
            self._clip_processor = None
        return self._clip_model, self._clip_processor

    def image_similarity(self, lost: dict[str, Any], found: dict[str, Any]) -> float | None:
        """Use CLIP image-image similarity, or image-text similarity if one photo is absent."""
        model, processor = self._load_clip()
        if model is None or processor is None:
            return None
        lost_path = Path(str(lost.get("image_path") or ""))
        found_path = Path(str(found.get("image_path") or ""))
        lost_has_image = bool(lost.get("image_path")) and lost_path.is_file()
        found_has_image = bool(found.get("image_path")) and found_path.is_file()
        if not lost_has_image and not found_has_image:
            return None
        try:
            import torch
            with torch.no_grad():
                if lost_has_image and found_has_image:
                    with Image.open(lost_path) as left_image, Image.open(found_path) as right_image:
                        pixels = processor(images=[left_image.convert("RGB"), right_image.convert("RGB")], return_tensors="pt")
                    embeddings = model.get_image_features(pixel_values=pixels["pixel_values"])
                    embeddings = torch.nn.functional.normalize(embeddings, dim=-1)
                    cosine = torch.sum(embeddings[0] * embeddings[1]).item()
                else:
                    image_path = lost_path if lost_has_image else found_path
                    text_report = found if lost_has_image else lost
                    with Image.open(image_path) as source:
                        pixels = processor(images=source.convert("RGB"), return_tensors="pt")
                    text_inputs = processor(text=[_text_value(text_report)], return_tensors="pt",
                                            padding=True, truncation=True)
                    image_embedding = model.get_image_features(pixel_values=pixels["pixel_values"])
                    text_embedding = model.get_text_features(
                        input_ids=text_inputs["input_ids"],
                        attention_mask=text_inputs.get("attention_mask"),
                    )
                    image_embedding = torch.nn.functional.normalize(image_embedding, dim=-1)
                    text_embedding = torch.nn.functional.normalize(text_embedding, dim=-1)
                    cosine = torch.sum(image_embedding[0] * text_embedding[0]).item()
            return max(0.0, min(1.0, (float(cosine) + 1.0) / 2.0))
        except Exception:
            return None

    def compare(self, lost: dict[str, Any], found: dict[str, Any]) -> dict[str, Any]:
        text_score, text_engine = self.text_similarity(_text_value(lost), _text_value(found))
        image_score = self.image_similarity(lost, found)
        lost_cat, found_cat = lost.get("category"), found.get("category")
        category_score = 1.0 if lost_cat and lost_cat == found_cat else (0.15 if not lost_cat or not found_cat else 0.0)
        location_score = _location_score(lost, found)
        time_score = _time_score(lost, found)

        weighted = [("text", text_score, 0.42 if image_score is not None else 0.50),
                    ("category", category_score, 0.18 if image_score is not None else 0.20)]
        if image_score is not None:
            weighted.append(("image", image_score, 0.20))
        if location_score is not None:
            weighted.append(("location", location_score, 0.10 if image_score is not None else 0.15))
        if time_score is not None:
            weighted.append(("time", time_score, 0.10 if image_score is not None else 0.15))
        total_weight = sum(weight for _, _, weight in weighted)
        score = sum(value * weight for _, value, weight in weighted) / max(total_weight, 0.001)

        reasons: list[str] = []

        # Prefer explanations that quote actual values recorded on both reports.
        category_names = {
            "stationery": "Stationery & books", "clothing": "Clothing", "bags_wallets": "Bags & wallets",
            "accessories": "Accessories", "electronics": "Electronics", "identity_documents": "Identity documents",
            "keys_access": "Keys & access cards", "cash_jewellery": "Cash & jewellery",
            "sports_instruments": "Sports equipment & instruments", "other": "Other",
        }
        if lost_cat and found_cat and lost_cat != found_cat:
            left_label = category_names.get(str(lost_cat), str(lost_cat).replace("_", " ").title())
            right_label = category_names.get(str(found_cat), str(found_cat).replace("_", " ").title())
            reasons.append(f"Categories differ: {left_label} vs {right_label}.")

        left_brand = str(lost.get("brand") or "").strip()
        right_brand = str(found.get("brand") or "").strip()
        def normal_brand(value: str) -> str:
            return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))
        if left_brand and right_brand:
            if normal_brand(left_brand) == normal_brand(right_brand):
                reasons.append(f"Brand matches: {right_brand}.")
            else:
                reasons.append(f"Reported brands differ: {left_brand} vs {right_brand}.")

        left_colour = str(lost.get("primary_color") or "").strip()
        right_colour = str(found.get("primary_color") or "").strip()
        if left_colour and right_colour:
            if set(tokens(left_colour)) == set(tokens(right_colour)):
                reasons.append(f"Colour matches: {right_colour}.")
            else:
                reasons.append(f"Reported colours differ: {left_colour} vs {right_colour}.")

        def clean_value(value):
            return " ".join(str(value or "").casefold().split())
        left_room, right_room = clean_value(lost.get("location_room")), clean_value(found.get("location_room"))
        left_area, right_area = clean_value(lost.get("location_area")), clean_value(found.get("location_area"))
        left_block, right_block = clean_value(lost.get("location_block")), clean_value(found.get("location_block"))
        left_floor, right_floor = clean_value(lost.get("location_floor")), clean_value(found.get("location_floor"))
        if left_room and right_room and left_room == right_room:
            reasons.append(f"Both reports mention room {str(found.get('location_room')).strip()}.")
        elif left_area and right_area and left_area == right_area:
            reasons.append(f"Both reports mention {str(found.get('location_area')).strip()}.")
        elif left_block and right_block and left_block == right_block:
            label = "Block " + str(found.get("location_block")).strip()
            if left_floor and right_floor and left_floor == right_floor:
                label += ", floor " + str(found.get("location_floor")).strip()
            reasons.append(f"Both reports place the item in {label}.")
        elif location_score is not None and location_score <= 0.2:
            left_place = str(lost.get("location_area") or lost.get("location_block") or "an unspecified location").strip()
            right_place = str(found.get("location_area") or found.get("location_block") or "an unspecified location").strip()
            if left_place != right_place:
                reasons.append(f"Reported locations differ: {left_place} vs {right_place}.")

        left_time, right_time = _parse_date(lost.get("occurred_at")), _parse_date(found.get("occurred_at"))
        if left_time and right_time:
            minutes_apart = int(round(abs((left_time - right_time).total_seconds()) / 60))
            if minutes_apart < 60:
                time_phrase = "within an hour" if minutes_apart < 5 else f"about {minutes_apart} minutes apart"
            elif minutes_apart < 24 * 60:
                hours_apart = int(round(minutes_apart / 60))
                time_phrase = f"about {hours_apart} hour{'s' if hours_apart != 1 else ''} apart"
            else:
                days_apart = int(round(minutes_apart / (24 * 60)))
                time_phrase = f"about {days_apart} day{'s' if days_apart != 1 else ''} apart"
            if minutes_apart <= 24 * 60 or (time_score is not None and time_score <= 0.2):
                reasons.append(f"Reported times are {time_phrase}.")

        left_features = set(tokens(str(lost.get("visible_features") or "")))
        right_features = set(tokens(str(found.get("visible_features") or "")))
        distinctive = {"scratch", "sticker", "zipper", "pocket", "pockets", "stripe", "logo", "crack",
                       "stain", "hinge", "case", "strap", "loop", "mark", "dent", "button", "screen",
                       "corner", "seam", "pattern", "silver", "gold", "white", "black", "blue", "red"}
        shared_features = sorted((left_features & right_features) & distinctive)
        if shared_features:
            reasons.append("Shared visible details: " + ", ".join(shared_features[:3]) + ".")

        if category_score >= 0.9 and not any(reason.startswith("Categories differ:") for reason in reasons):
            reasons.append("Both reports use the same item category.")
        if text_score >= 0.34 and not shared_features and not any(reason.startswith("Brand matches:") for reason in reasons):
            overlap = sorted(word for word in set(tokens(_text_value(lost))) & set(tokens(_text_value(found))) if len(word) >= 4)
            if overlap:
                reasons.append("Shared description terms: " + ", ".join(overlap[:3]) + ".")
            elif text_engine == "sentence_embeddings":
                reasons.append("The descriptions are semantically similar according to sentence embeddings.")
        if image_score is not None and image_score >= 0.70:
            reasons.append("The available photos have visually compatible content (CLIP image similarity).")
        elif image_score is not None and image_score <= 0.30:
            reasons.append("The available photos are visually dissimilar (CLIP image similarity).")
        if not reasons:
            reasons.append("There is limited overlap in recorded details; review the candidate manually.")

        strength = "strong" if score >= 0.72 else ("possible" if score >= 0.45 else "limited")
        engine = text_engine + (" + CLIP" if image_score is not None else "")
        return {
            "score": round(score, 4),
            "strength": strength,
            "reasons": reasons[:5],
            "signals": {
                "text": round(text_score, 4),
                "image": None if image_score is None else round(image_score, 4),
                "category": round(category_score, 4),
                "location": None if location_score is None else round(location_score, 4),
                "time": None if time_score is None else round(time_score, 4),
            },
            "engine": engine,
        }

    def rank(self, lost: dict[str, Any], found_reports: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
        ranked = []
        for report in found_reports:
            result = self.compare(lost, report)
            ranked.append({"report": report, **result})
        ranked.sort(key=lambda item: item["score"], reverse=True)
        return ranked[:limit]


matching_engine = MatchingEngine()
