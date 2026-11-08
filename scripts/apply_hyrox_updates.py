#!/usr/bin/env python3
"""RACE//RADAR : applique uniquement des annonces HYROX saisies et validées.

Aucune requête réseau. Ne collecte pas hyrox.com et ne devine pas d'ouverture.
"""
from __future__ import annotations
import argparse
from datetime import date
import json
from pathlib import Path
from urllib.parse import urlsplit
import re

ALLOWED_HOSTS = {"hyrox.com", "www.hyrox.com", "hyroxfrance.com", "www.hyroxfrance.com"}
NEARBY = {"bâle", "basel", "francfort", "frankfurt", "fribourg-en-brisgau", "freiburg", "karlsruhe", "offenburg", "stuttgart", "baden-baden"}
REGISTRATION = {"announced", "open", "waitlist", "sold_out"}


def check_date(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} : date ISO YYYY-MM-DD requise")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{label} : date ISO YYYY-MM-DD requise") from None
    if parsed.isoformat() != value:
        raise ValueError(f"{label} : date ISO YYYY-MM-DD requise")
    return value


def official_url(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("source_url : une URL HYROX officielle est requise")
    parts = urlsplit(value)
    if parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS or parts.username or parts.password:
        raise ValueError("source_url : utiliser une URL https://hyrox.com/ ou hyroxfrance.com officielle")
    if not (parts.path.startswith("/event/") or parts.path.startswith("/fr/event/")):
        raise ValueError("source_url : fournir de préférence la page de l'événement, pas le calendrier général")
    return value


def new_event_allowed(u: dict) -> bool:
    country = u.get("country", "")
    if country == "FR":
        return True
    if country in {"DE", "CH"} and str(u.get("city", "")).strip().lower() in NEARBY:
        return True
    return False


def create_event(u: dict) -> dict:
    for key in ["name", "city", "date", "end", "country"]:
        if not u.get(key):
            raise ValueError(f"Nouvel événement {u['id']} : champ requis {key}")
    if not new_event_allowed(u):
        raise ValueError("Nouvel événement hors du périmètre France / voisins sélectionnés")
    start, end = check_date(u["date"], "date"), check_date(u["end"], "end")
    if end < start:
        raise ValueError("end avant date")
    country = u["country"]
    return {
        "id": u["id"], "name": u["name"].strip(), "city": u["city"].strip(),
        "date": start, "end": end, "country": country,
        "url": u["source_url"], "location": ("France" if country == "FR" else "Proximité Strasbourg"),
        "status": "Ouverture non annoncée", "open_date": None,
        "young": "youngstars" in u["name"].lower(),
    }


def apply(data: dict, updates: dict, checked_date: str) -> tuple[dict, int]:
    if not isinstance(data.get("hyrox"), list):
        raise ValueError("events.json : liste hyrox absente")
    if not isinstance(updates, dict) or not isinstance(updates.get("updates"), list):
        raise ValueError("hyrox_updates.json : champ 'updates' (liste) requis")
    by_id = {x["id"]: x for x in data["hyrox"]}
    count = 0
    for u in updates["updates"]:
        if not isinstance(u, dict) or not re.fullmatch(r"h[0-9]{1,4}", str(u.get("id", ""))):
            raise ValueError("id attendu : h1, h2, ...")
        identifier = u["id"]
        registration = u.get("registration")
        if registration not in REGISTRATION:
            raise ValueError(f"{identifier} : registration doit être announced/open/waitlist/sold_out")
        source = official_url(u.get("source_url", ""))
        cat = u.get("category", "")
        if not isinstance(cat, str) or len(cat) > 45:
            raise ValueError(f"{identifier} : category invalide")
        cat = cat.strip()
        opening = u.get("open_date")
        if registration == "announced" and not opening:
            raise ValueError(f"{identifier} : open_date exigée pour announced")
        if opening is not None:
            opening = check_date(opening, "open_date")
        if registration == "waitlist" and opening is not None:
            raise ValueError(f"{identifier} : ne pas donner une date non annoncée")
        if identifier in by_id:
            event = by_id[identifier]
            if "date" in u or "end" in u:
                raise ValueError(f"{identifier} : dates événement existant à corriger séparément après vérification")
        else:
            event = create_event(u)
            # Ne pas créer deux entrées avec le même nom/ville/date.
            if any((x["name"].casefold(),x["city"].casefold(),x["date"]) == (event["name"].casefold(),event["city"].casefold(),event["date"]) for x in data["hyrox"]):
                raise ValueError(f"{identifier} : événement déjà présent sous un autre id")
            data["hyrox"].append(event)
            by_id[identifier] = event
        label = {
            "announced": "Ouverture annoncée",
            "open": "Billetterie ouverte",
            "waitlist": "Ouverture non annoncée",
            "sold_out": "Complet",
        }[registration]
        if cat and registration != "waitlist":
            label += " — " + cat
        before = (event.get("status"),event.get("open_date"),event.get("url"),event.get("registration_category"))
        event["status"] = label
        if opening is not None or registration == "waitlist":
            event["open_date"] = opening
        event["url"] = source
        event["registration_category"] = cat or None
        event["registration_source"] = source
        after = (event.get("status"),event.get("open_date"),event.get("url"),event.get("registration_category"))
        if before != after or event.get("registration_verified_at") is None:
            event["registration_verified_at"] = checked_date
            count += 1
    if count:
        data["hyrox"].sort(key=lambda x:(x["date"], x["name"]))
        data["hyroxUpdatedAt"] = checked_date
        data["asOf"] = checked_date
    return data,count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("events.json"))
    parser.add_argument("--updates", type=Path, default=Path("hyrox_updates.json"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    data = json.loads(args.data.read_text(encoding="utf-8"))
    updates = json.loads(args.updates.read_text(encoding="utf-8"))
    data,n = apply(data,updates,date.today().isoformat())
    print(f"HYROX : {len(updates['updates'])} annonces fournies ; {n} fiche(s) nouvelle(s) ou modifiée(s).")
    print("HYROX : source = annonces saisies manuellement ; aucune collecte automatisée du site officiel.")
    if args.dry_run:
        print("MODE TEST : aucun fichier modifié.")
    elif n:
        args.data.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    else:
        print("Aucun changement à enregistrer.")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
