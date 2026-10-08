import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.settings import Settings, settings
from app.core.demo_login import DEMO_ROLES
from app.core.object_store import AzureStore, object_store


def test_demo_role_logins_use_real_accounts_and_hide_passwords():
    with TestClient(app) as client:
        result = client.get('/api/v1/auth/demo-accounts')
        assert result.status_code == 200
        assert result.headers['cache-control'] == 'no-store'
        assert {x['role'] for x in result.json()['items']} == set(DEMO_ROLES)
        saved = json.loads(Path(settings().demo_credentials_path).read_text())
        for role in DEMO_ROLES:
            assert saved[role]['password'] not in result.text
            login = client.post('/api/v1/auth/demo-login', json={'role': role})
            assert login.status_code == 200
            me = client.get('/api/v1/me').json()
            assert me['role'] == role and me['id'] == saved[role]['user_id']
            if role == 'maintenance_technician':
                assert {grant['zone_code'] for grant in me['grants']} == {'WARD_A'}
        assert client.post('/api/v1/auth/demo-login', json={'role': 'monitor_service'}).status_code == 422
        assert client.post('/api/v1/auth/demo-login', json={'role': 'hospital_admin', 'password': 'override'}).status_code == 422
        assert client.post('/api/v1/auth/demo-login', json={'role': 'hospital_admin'},
                           headers={'Origin': 'https://outside.example'}).status_code == 403


def test_production_disables_demo_selection_and_login(monkeypatch):
    monkeypatch.setattr(settings(), 'app_mode', 'production')
    with TestClient(app) as client:
        assert client.get('/api/v1/auth/demo-accounts').json() == {'enabled': False, 'items': []}
        assert client.post('/api/v1/auth/demo-login', json={'role': 'hospital_admin'}).status_code == 403


def test_azure_adapter_private_prefix_checksum_and_scoped_enumeration():
    config = Settings(_env_file=None, object_storage_provider='azure',
                      azure_storage_connection_string='test-only-placeholder',
                      azure_storage_container='shared-test', azure_storage_prefix='hospital-greenops/')
    with patch('azure.storage.blob.BlobServiceClient.from_connection_string') as factory:
        container = factory.return_value.get_container_client.return_value
        container.get_container_properties.return_value = {'public_access': None}
        store = object_store(config)
        store.ensure_container()
        container.create_container.assert_not_called()
        body = b'synthetic artifact'
        metadata = {'sha256': hashlib.sha256(body).hexdigest()}
        store.put('tenant/world/evidence/hash', body, 'text/plain', metadata)
        call = container.upload_blob.call_args.kwargs
        assert call['name'] == 'hospital-greenops/tenant/world/evidence/hash'
        assert call['metadata'] == metadata and call['content_settings'].content_type == 'text/plain'
        container.download_blob.return_value.readall.return_value = body
        assert store.get('tenant/world/evidence/hash') == body
        container.download_blob.assert_called_with('hospital-greenops/tenant/world/evidence/hash')
        blob = MagicMock();blob.name='hospital-greenops/tenant/world/evidence/hash'
        container.list_blobs.return_value=[blob]
        assert [item.key for item in store.objects()] == ['tenant/world/evidence/hash']
        container.list_blobs.assert_called_with(name_starts_with='hospital-greenops/')
        container.get_container_properties.return_value={'public_access':'blob'}
        with pytest.raises(ValueError, match='private'):store.probe()


def test_azure_missing_credentials_and_empty_prefix_fail_closed():
    with pytest.raises(ValueError, match='required'):
        AzureStore(Settings(_env_file=None, object_storage_provider='azure', azure_storage_connection_string='', azure_storage_account_url='', azure_storage_account_key=''))
    with patch('azure.storage.blob.BlobServiceClient.from_connection_string'):
        with pytest.raises(ValueError, match='prefix'):
            AzureStore(Settings(_env_file=None, azure_storage_connection_string='test-only', azure_storage_prefix=''))


def test_runtime_can_read_hosted_static_metadata_with_rls():
    from sqlalchemy import text
    from sqlalchemy.exc import ProgrammingError
    from app.core.db import Session
    with Session.begin() as db:
        assert db.scalar(text('SELECT version_num FROM alembic_version')) == '0006'
        assert db.scalar(text('SELECT count(*) FROM metric_catalog')) >= 7
        assert db.scalar(text('SELECT count(*) FROM observations')) == 0
    with pytest.raises(ProgrammingError) as denied:
        with Session.begin() as db:
            db.execute(text("INSERT INTO metric_catalog(code,domain,unit,semantics,aggregation) VALUES ('unauthorized','x','x','x','x')"))
    assert denied.value.orig.sqlstate == '42501'

    from app.cli import demo_principal
    from app.core.db import transaction
    principal = demo_principal()
    with transaction(principal.user_id, principal.organization_id) as db:
        assert db.scalar(text("SELECT setting::int FROM pg_settings WHERE name='statement_timeout'")) == settings().database_statement_timeout_ms
