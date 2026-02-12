#!/usr/bin/env python3
"""Fetch badges from Credly API and write `badges.yml`.

Environment variables supported:
- `CREDLY_TOKEN` : personal access token (preferred)
- `CREDLY_CLIENT_ID` and `CREDLY_CLIENT_SECRET` : client credentials (optional)
- `CREDLY_USER` : Credly username/slug (default: pinak-meher)

This script is defensive about response shapes and will try to extract
badge name, image URL and badge page URL.
"""
from __future__ import annotations
import os
import sys
import pathlib
import requests
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'badges.yml'

CLIENT_ID = os.getenv('CREDLY_CLIENT_ID')
CLIENT_SECRET = os.getenv('CREDLY_CLIENT_SECRET')
TOKEN = os.getenv('CREDLY_TOKEN')
USER = os.getenv('CREDLY_USER', 'pinak-meher')

def get_token_from_client_credentials(client_id: str, client_secret: str) -> str | None:
    url = 'https://api.credly.com/oauth2/token'
    try:
        r = requests.post(url, data={
            'grant_type': 'client_credentials',
            'client_id': client_id,
            'client_secret': client_secret,
        }, timeout=15)
        r.raise_for_status()
        data = r.json()
        return data.get('access_token')
    except Exception as e:
        print('Failed to get token from client credentials:', e, file=sys.stderr)
        return None

def fetch_badges(token: str, username: str):
    headers = {'Authorization': f'Bearer {token}'}

    # Best-effort endpoint — Credly API versions vary. This is a common pattern.
    endpoints = [
        f'https://api.credly.com/v1.1/users/{username}/badges',
        f'https://api.credly.com/v1/users/{username}/badges',
        f'https://api.credly.com/v1.1/members/{username}/badges',
        f'https://api.credly.com/v1/members/{username}/badges',
    ]

    for ep in endpoints:
        try:
            r = requests.get(ep, headers=headers, timeout=15)
            if r.status_code == 404:
                continue
            r.raise_for_status()
            return r.json()
        except requests.HTTPError as e:
            # try next endpoint
            continue
        except Exception as e:
            print('Error fetching from', ep, e, file=sys.stderr)
            continue

    print('All endpoints failed. Credly API may have a different path or require different scopes.', file=sys.stderr)
    return None

def extract_badges_from_response(json_data):
    badges = []
    if not json_data:
        return badges

    # Common patterns: top-level 'data' list, or 'elements', or plain list
    candidates = []
    if isinstance(json_data, dict):
        for key in ('data', 'elements', 'results', 'badges'):
            if key in json_data and isinstance(json_data[key], (list, tuple)):
                candidates = json_data[key]
                break
        # fallback: if dict contains items that look like badges
        if not candidates:
            for v in json_data.values():
                if isinstance(v, list):
                    candidates = v
                    break
    elif isinstance(json_data, list):
        candidates = json_data

    for item in candidates:
        # item may wrap badge details under 'badge' or 'credential'
        badge = None
        if isinstance(item, dict):
            if 'badge' in item and isinstance(item['badge'], dict):
                badge = item['badge']
            elif 'credential' in item and isinstance(item['credential'], dict):
                badge = item['credential']
            else:
                badge = item

        if not isinstance(badge, dict):
            continue

        # try multiple common field names
        name = badge.get('name') or badge.get('title') or badge.get('badge_title') or ''
        image = badge.get('image_url') or badge.get('image') or badge.get('badge_image') or ''
        url = badge.get('url') or badge.get('badge_url') or badge.get('public_url') or ''

        # normalize image src
        if image and image.startswith('//'):
            image = 'https:' + image

        if not image:
            # sometimes nested under 'images' list
            imgs = badge.get('images') or badge.get('imageUrls') or None
            if isinstance(imgs, (list, tuple)) and imgs:
                image = imgs[0]

        if not url and badge.get('id'):
            url = f'https://www.credly.com/users/{USER}/badges/{badge.get("id")}'

        if image:
            badges.append({'name': name or 'Credly Badge', 'image': image, 'url': url or f'https://www.credly.com/users/{USER}', 'width': 100})

    return badges

def write_yaml(badges):
    data = {'badges': badges}
    with open(OUT, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, sort_keys=False, allow_unicode=True)

def main():
    token = TOKEN
    if not token and CLIENT_ID and CLIENT_SECRET:
        token = get_token_from_client_credentials(CLIENT_ID, CLIENT_SECRET)

    if not token:
        print('No Credly credentials found. Set CREDLY_TOKEN or CREDLY_CLIENT_ID/CREDLY_CLIENT_SECRET.', file=sys.stderr)
        sys.exit(2)

    json_data = fetch_badges(token, USER)
    if not json_data:
        print('Failed to fetch badges from Credly API.', file=sys.stderr)
        sys.exit(3)

    badges = extract_badges_from_response(json_data)
    if not badges:
        print('No badges found in API response. Response shape may be different.', file=sys.stderr)
        sys.exit(4)

    write_yaml(badges)
    print(f'Wrote {len(badges)} badges to {OUT}')

if __name__ == '__main__':
    main()
