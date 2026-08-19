#!/usr/bin/env python3
"""
The entirety of this script is a modified version built on laurorual's.
Verifies the side a mod belongs to by several processes;
    Internal metadata (Fabric/Quilt/Forge) > Modrinth > CurseForge.
Requires Python 3.8+ and requests, tqdm, and tomli (optional for Python ≥ 3.11).
"""

import os
import re
import sys
import json
import zipfile
import shutil
import argparse
from typing import Optional, Dict, List, Tuple

import requests
from tqdm import tqdm

# Attempts to import tomllib (Python 3.11+); otherwise, use tomli
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None
        print("Warning: 'tomli' is not installed. Metadata extraction from Forge mods will be less accurate.",
              file=sys.stderr)

# ----------------------------------------------------------------------
# API Settings
MODRINTH_API = "https://api.modrinth.com/v2"
MODRINTH_SEARCH = f"{MODRINTH_API}/search"
CURSEFORGE_API = "https://api.curseforge.com/v1"
CURSEFORGE_GAME_ID = 432
USER_AGENT = "ModSideChecker/3.0 (contato@exemplo.com)"

CF_CAT_CLIENT = 428
CF_CAT_SERVER = 429
API_KEY_FILE = "curseforge_api_key.txt"

# ----------------------------------------------------------------------
def load_saved_api_key() -> Optional[str]:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    key_path = os.path.join(script_dir, API_KEY_FILE)
    if os.path.isfile(key_path):
        with open(key_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return None

def save_api_key(key: str):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    key_path = os.path.join(script_dir, API_KEY_FILE)
    with open(key_path, 'w', encoding='utf-8') as f:
        f.write(key.strip())

def delete_api_key_file():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    key_path = os.path.join(script_dir, API_KEY_FILE)
    if os.path.isfile(key_path):
        os.remove(key_path)

def prompt_for_api_key() -> Optional[str]:
    saved_key = load_saved_api_key()
    if saved_key:
        tqdm.write("CurseForge save key found.")
        choice = input("Type a new key, press Enter to use the saved one, "
                       "or 'none' to skip CurseForge:").strip()
        if choice.lower() == 'none':
            delete_api_key_file()
            tqdm.write("Key removed. Disabled fallback to CurseForge.")
            return None
        elif choice == '':
            tqdm.write("Using saved key.")
            return saved_key
        else:
            save_api_key(choice)
            tqdm.write("New key has been saved.")
            return choice
    else:
        choice = input("Enter your CurseForge API key (or leave it blank to skip): ").strip()
        if choice:
            save_api_key(choice)
            tqdm.write("Key saved for future use.")
            return choice
        else:
            tqdm.write("No key has been provided. Disabled fallback to CurseForge.")
            return None

# ----------------------------------------------------------------------
def slugify(text: str) -> str:
    cleaned = re.sub(r'[^\w\s-]', '', text).strip().lower()
    return re.sub(r'[\s]+', '-', cleaned)

def extract_manifest_title(jar_path: str) -> Optional[str]:
    try:
        with zipfile.ZipFile(jar_path, 'r') as zf:
            with zf.open('META-INF/MANIFEST.MF') as manifest:
                for line in manifest.read().decode('utf-8').splitlines():
                    if line.strip().lower().startswith('specification-title:'):
                        parts = line.split(':', 1)
                        if len(parts) > 1:
                            return parts[1].strip()
    except Exception:
        pass
    return None

def extract_metadata(jar_path: str) -> Dict[str, Optional[str]]:
    """
    Returns a dictionary containing:
        'name'   : human-readable name (fabric/quilt/forge) or None
        'title'  : Specification-Title from MANIFEST.MF or None
        'slug'   : slug identifier (e.g., modid)
        'env'    : 'client', 'server', 'both', or None if not specified
                   ( '*' is treated as 'both' )
    """
    result = {'name': None, 'title': None, 'slug': None, 'env': None}
    try:
        with zipfile.ZipFile(jar_path, 'r') as zf:
            # 1. Fabric / Quilt
            for meta_file in ('fabric.mod.json', 'quilt.mod.json'):
                try:
                    data = json.loads(zf.read(meta_file))
                    name = data.get('name')
                    if name:
                        result['name'] = name
                    modid = data.get('id')
                    if modid:
                        result['slug'] = modid
                    env = data.get('environment', '*')
                    if env == '*':
                        result['env'] = 'both'
                    elif env in ('client', 'server'):
                        result['env'] = env
                    # If 'environment' exists but has a different value, it is ignored (None)
                    return result
                except (KeyError, json.JSONDecodeError):
                    continue

            # 2. Forge (mods.toml)
            if tomllib:
                try:
                    toml_data = tomllib.loads(zf.read('META-INF/mods.toml').decode('utf-8'))
                    mods = toml_data.get('mods', [])
                    if mods:
                        first = mods[0]
                        modid = first.get('modId')
                        display = first.get('displayName')
                        if modid:
                            result['slug'] = modid
                            if display:
                                result['name'] = display
                            side = first.get('side', 'BOTH').upper()
                            if side == 'CLIENT':
                                result['env'] = 'client'
                            elif side == 'SERVER':
                                result['env'] = 'server'
                            else:
                                result['env'] = 'both'
                            return result
                except Exception:
                    pass

            # 3. mcmod.info (legacy) – does not have reliable info
            try:
                data = json.loads(zf.read('mcmod.info'))
                if isinstance(data, list) and data:
                    modid = data[0].get('modid')
                    name = data[0].get('name')
                    if modid:
                        result['slug'] = modid
                    if name:
                        result['name'] = name
                    return result
            except Exception:
                pass

    except (zipfile.BadZipFile, IOError):
        pass

    # Fallback: MANIFEST.MF Title
    title = extract_manifest_title(jar_path)
    result['title'] = title

    # If there is no slug, generate one from the filename
    if not result['slug']:
        result['slug'] = slugify(os.path.splitext(os.path.basename(jar_path))[0])
    return result

# ----------------------------------------------------------------------
def modrinth_search_slug(slug: str) -> Optional[str]:
    url = f"{MODRINTH_API}/project/{slug}"
    headers = {'User-Agent': USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        client = data.get('client_side', 'unknown')
        server = data.get('server_side', 'unknown')
        client_ok = client in ('required', 'optional')
        server_ok = server in ('required', 'optional')
        client_no = client == 'unsupported'
        server_no = server == 'unsupported'
        if client_ok and server_ok:
            return 'both'
        if client_ok and server_no:
            return 'client'
        if client_no and server_ok:
            return 'server'
        return None
    except requests.RequestException:
        return None

def modrinth_search_text(query: str) -> Optional[str]:
    params = {'query': query, 'limit': 1}
    headers = {'User-Agent': USER_AGENT}
    try:
        resp = requests.get(MODRINTH_SEARCH, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        hits = resp.json().get('hits', [])
        if not hits:
            return None
        slug = hits[0].get('slug')
        if slug:
            return modrinth_search_slug(slug)
    except requests.RequestException:
        pass
    return None

def check_modrinth(terms: List[str]) -> Optional[str]:
    for term in terms:
        side = modrinth_search_slug(term)
        if side:
            return side
        side = modrinth_search_text(term)
        if side:
            return side
    return None

def check_curseforge(terms: List[str], api_key: str) -> Optional[str]:
    if not api_key:
        return None
    headers = {
        'x-api-key': api_key,
        'Accept': 'application/json',
    }
    for term in terms:
        search_url = f"{CURSEFORGE_API}/mods/search"
        params = {
            'gameId': CURSEFORGE_GAME_ID,
            'searchFilter': term,
            'pageSize': 1,
        }
        try:
            resp = requests.get(search_url, headers=headers, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json().get('data', [])
            if data:
                mod_id = data[0]['id']
                details_url = f"{CURSEFORGE_API}/mods/{mod_id}"
                resp = requests.get(details_url, headers=headers, timeout=10)
                resp.raise_for_status()
                mod = resp.json().get('data', {})
                categories = mod.get('categories', [])
                cat_ids = {c['id'] for c in categories}
                is_client = CF_CAT_CLIENT in cat_ids
                is_server = CF_CAT_SERVER in cat_ids
                if is_client and is_server:
                    return 'both'
                if is_client:
                    return 'client'
                if is_server:
                    return 'server'
        except requests.RequestException:
            continue
    return None

def verify_mod(jar_path: str, cf_api_key: Optional[str]) -> Tuple[str, str]:
    filename = os.path.basename(jar_path)
    meta = extract_metadata(jar_path)

    # 1. Verify if the metadata itself already defines its side
    env = meta.get('env')
    if env is not None and env in ('client', 'server', 'both'):
        tqdm.write(f"  {filename}: side defined for mod: {env}")
        return filename, env

    # If you've arrived here, you need to search online
    # Prepare a list of search terms (already used in the fallback functions)

    search_terms = []
    if meta.get('name'):
        search_terms.append(meta['name'])
    if meta.get('title'):
        search_terms.append(meta['title'])
    slug = meta.get('slug')
    if slug:
        if slug not in search_terms:
            search_terms.append(slug)
    file_term = os.path.splitext(filename)[0]
    file_term_clean = re.sub(r'[-_](v?\d+[\.\d]*).*', '', file_term)
    if file_term_clean and file_term_clean not in search_terms:
        search_terms.append(file_term_clean)

    tqdm.write(f"  {filename}: termos={search_terms}")

    # 2. Modrinth
    side = check_modrinth(search_terms)
    if side:
        tqdm.write(f"  Modrinth: {side}")
        return filename, side

    # 3. CurseForge
    if cf_api_key:
        tqdm.write(f"  Checking CurseForge...")
        side = check_curseforge(search_terms, cf_api_key)
        if side:
            tqdm.write(f"  CurseForge: {side}")
            return filename, side
        else:
            tqdm.write("  CurseForge: not found.")
    else:
        tqdm.write("  CurseForge: disabled.")

    return filename, 'unknown'

# ----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Check side of a Minecraft mod.")
    parser.add_argument('--dir', default='.', help="Directory where the .jar files are located (default: current directory).")
    args = parser.parse_args()
    target_dir = os.path.abspath(args.dir)

    cf_api_key = prompt_for_api_key()

    jar_files = sorted([f for f in os.listdir(target_dir) if f.endswith('.jar')])
    if not jar_files:
        print("No .jar files found.")
        return

    total = len(jar_files)
    tqdm.write(f"\nFound {total} mods to check.\n")

    results = []
    progress = tqdm(jar_files, desc="Checking mods", unit="mod", dynamic_ncols=True)

    try:
        for fname in progress:
            full_path = os.path.join(target_dir, fname)
            progress.set_postfix_str(fname)
            name, side = verify_mod(full_path, cf_api_key)
            results.append((name, side))
            progress.update(1)
    except KeyboardInterrupt:
        tqdm.write("\nInterrupted by user. Generating partial results...")
    finally:
        progress.close()

    client_mods = [name for name, side in results if side == 'client']
    kept_mods = [name for name, side in results if side != 'client']

    mods_dir = target_dir
    instance_dir = os.path.dirname(mods_dir)
    instance_name = os.path.basename(instance_dir)
    parent_dir = os.path.dirname(instance_dir)

    dest_dir = os.path.join(parent_dir, f"{instance_name}_serverside")

    if os.path.exists(dest_dir):
        print(f"Destination already exists: {dest_dir}")
        return

    shutil.copytree(instance_dir, dest_dir)

    dest_mods_dir = os.path.join(dest_dir, 'mods')
    for name in client_mods:
        target = os.path.join(dest_mods_dir, name)
        if os.path.isfile(target):
            os.remove(target)
        else:
            tqdm.write(f"Warning: {name} not found in copy.")

    output_file = os.path.join(dest_dir, 'removed_mods.txt')
    with open(output_file, 'w', encoding='utf-8') as f:
        for name in sorted(client_mods):
            f.write(f"{name}\n")

    print(f"\nServer-side copy stored in: {dest_dir}")
    print(f"{len(client_mods)} client-side mod(s) removed.")
    print(f"Removed mods list stored in: {output_file}")

if __name__ == '__main__':
    main()