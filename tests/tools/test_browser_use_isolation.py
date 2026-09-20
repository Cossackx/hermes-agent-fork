"""Public isolation exercises real session routing, not just the outer selector."""
import json

from tools import browser_use_cli as bu
from tools import browser_tool_session as sessions


def test_isolated_route_bypasses_profile_and_overrides(monkeypatch):
    seen = []
    def forbidden(*args, **kwargs):
        raise AssertionError('account/cloud route used')
    monkeypatch.setattr(sessions._real_profile, '_real_profile_cdp', forbidden)
    monkeypatch.setattr(sessions._cloud, '_get_cloud_provider', forbidden)
    monkeypatch.setattr(sessions._cdp, '_get_cdp_override', lambda: 'ws://account')
    monkeypatch.setattr(sessions._bt, '_is_browser_use_cli_mode', lambda: False)
    def run(key, command, args, **kwargs):
        assert sessions._bt._is_local_sidecar_key(key)
        info = sessions._create_session_for_key(key, force_local=True)
        assert not info['features'].get('real_profile')
        assert info['cdp_url'] is None
        seen.append(key)
        return {'success': True, 'data': {'cdpUrl': 'ws://clean'}}
    monkeypatch.setattr(sessions, '_run_browser_command', run)
    env = {'BU_CDP_WS': 'ws://account', 'BU_CDP_URL': 'http://account'}
    assert bu._route_backend(env, 'research', 'task', False, True) is None
    assert env['BU_CDP_WS'] == 'ws://clean'
    assert 'BU_CDP_URL' not in env
    assert env['BU_NAME'].startswith('hermes-isolated-')
    assert len(seen) == 1
    assert bu._isolated_route_session('x' * 63 + 'a') != bu._isolated_route_session('x' * 63 + 'b')
    assert bu._isolated_route_session('') != bu._isolated_route_session('default')
    refusal = json.loads(bu.browser_exec('print(1)', session=env['BU_NAME']))
    assert 'reserved' in refusal['error']


def test_isolated_failure_never_falls_through(monkeypatch):
    monkeypatch.setattr(sessions, '_run_browser_command', lambda *a, **k: {'success': False, 'error': 'fixture failed'})
    monkeypatch.setattr(bu, '_resolve_real_profile_cdp', lambda *a, **k: (_ for _ in ()).throw(AssertionError('fallback')))
    env = {'BU_CDP_WS': 'ws://account'}
    assert 'fixture failed' in bu._route_backend(env, 'r', None, False, True)
    assert 'BU_CDP_WS' not in env
