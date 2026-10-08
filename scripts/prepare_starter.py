#!/usr/bin/env python3
"""Preserve source evidence and emit an explicitly allowlisted runtime bundle."""
import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

PUBLIC_CONFIG = {'facility_id', 'facility_type', 'source_type', 'seed', 'days', 'stress', 'bed_capacity',
                 'interval_semantics', 'tank_usable_l', 'essential_water_lph', 'battery_deliverable_kwh',
                 'essential_load_kw', 'waste_note'}
PUBLIC_FILES = ['data/observations.csv', 'data/stress_observations.csv', 'data/validation.json',
                'artifacts/evaluation.json', 'artifacts/model_registry.json', 'artifacts/demo_scenarios.json',
                'RESULTS.md'] + [f'artifacts/{t}_{h}h.joblib' for t in ('energy_kwh', 'water_l') for h in (1, 6, 24)] + ['artifacts/anomaly.joblib']

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def prepare(source, research, public):
    source, research, public = map(Path, (source, research, public))
    if source.is_file():
        with zipfile.ZipFile(source) as z:
            for entry in z.infolist():
                dest = research.parent / entry.filename
                if not dest.resolve().is_relative_to(research.parent.resolve()):
                    raise ValueError('Unsafe archive member')
            z.extractall(research.parent)
        extracted = research.parent / 'hospital_greenops_starter'
        if extracted != research:
            shutil.copytree(extracted, research, dirs_exist_ok=True)
    elif source.is_dir():
        if source.resolve() != research.resolve():
            shutil.copytree(source, research, dirs_exist_ok=True)
    else:
        raise FileNotFoundError(f'{source}: supply ZIP or --source-dir hospital_greenops_starter')
    original = json.loads((research / 'MANIFEST.json').read_text())
    for f in original['files']:
        if sha(research / f['path']) != f['sha256']:
            raise ValueError(f"Checksum mismatch: {f['path']}")
    public.mkdir(parents=True, exist_ok=True)
    for rel in PUBLIC_FILES:
        dest = public / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(research / rel, dest)
    for name in ('facility.json', 'stress_facility.json'):
        value = json.loads((research / 'data' / name).read_text())
        (public / 'data' / name).write_text(json.dumps({k: value[k] for k in PUBLIC_CONFIG if k in value}, indent=2))
    manifest = {'sanitizer_version': 1, 'original_manifest_sha256': sha(research / 'MANIFEST.json'),
                'source_format': 'directory' if source.is_dir() else 'zip',
                'source_archive_sha256': sha(source) if source.is_file() else None,
                'files': [{'path': str(p.relative_to(public)), 'sha256': sha(p), 'bytes': p.stat().st_size}
                          for p in sorted(public.rglob('*')) if p.is_file() and p.name != 'MANIFEST.json']}
    (public / 'MANIFEST.json').write_text(json.dumps(manifest, indent=2))
    for rel in ('data/private_labels.csv', 'data/stress_private_labels.csv'):
        dest = research.parent / 'evaluation' / Path(rel).name
        dest.parent.mkdir(exist_ok=True)
        shutil.copy2(research / rel, dest)
    print(json.dumps({'verified_original_files': len(original['files']), 'public_files': len(manifest['files']),
                      'public_manifest_sha256': sha(public / 'MANIFEST.json')}))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive')
    parser.add_argument('--source-dir')
    parser.add_argument('--research-out', default='research/starter')
    parser.add_argument('--public-out', default='data/public/starter')
    args = parser.parse_args()
    prepare(args.archive or args.source_dir or 'hospital_greenops_starter', args.research_out, args.public_out)
