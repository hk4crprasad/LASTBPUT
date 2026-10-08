"""Demo-only account selection; passwords never enter the client bundle."""
import json
from pathlib import Path
from typing import Literal
from fastapi import HTTPException
from app.core.settings import settings

DemoRole = Literal['organization_admin', 'hospital_admin', 'operations_supervisor',
                   'maintenance_technician', 'waste_officer', 'sustainability_officer', 'auditor']
DEMO_ROLES = {
    'hospital_admin': ('Hospital admin', 'Facility configuration and operational oversight'),
    'organization_admin': ('Organization admin', 'Organization administration and policy'),
    'operations_supervisor': ('Operations supervisor', 'Resource operations and accountable actions'),
    'maintenance_technician': ('Maintenance technician', 'Assigned maintenance in Ward A'),
    'waste_officer': ('Waste officer', 'Waste batches, pickups and handover evidence'),
    'sustainability_officer': ('Sustainability officer', 'Cost, carbon assumptions and scenarios'),
    'auditor': ('Auditor', 'Read operations and generate evidence reports'),
}

def credentials():
    if settings().app_mode != 'demo':
        raise HTTPException(403, 'Demo sign-in is disabled outside demo mode')
    try:
        data = json.loads(Path(settings().demo_credentials_path).read_text())
        for role in DEMO_ROLES:
            row = data[role]
            if row['email'] != role + '@demo.greenops.local' or not row['password'] or not row['user_id']:
                raise ValueError('Invalid demo identity')
        return data
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(503, 'Demo credentials unavailable; run demo bootstrap') from None
