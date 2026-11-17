#!/usr/bin/env python3
"""Exercise a candidate on loopback, with a disposable database only."""
import json
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

base = sys.argv[1]
if base != 'http://127.0.0.1:18791':
    raise SystemExit('This write probe is restricted to the disposable candidate port')


def request(path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(base + path, data=data, headers={'Content-Type': 'application/json', 'Origin': base})
    with urlopen(req, timeout=8) as response:
        return json.load(response)


health = request('/api/health')
assert health['engine_available']
assert health['revision'] == sys.argv[2][:12], 'Candidate revision does not match'
seed = request('/api/idea', {'content': 'Deploy check: Grădină 🌱 "quotes" C:\\notes\nline'})
for mutation in ['expand', 'rephrase', 'mutate_keywords', 'synthesize']:
    result = request('/api/idea', {'parent_id': seed['id'], 'mutation': mutation})
    assert result['parent_id'] == seed['id'] and result['depth'] == 1
    assert result['content'] and not result['content'].startswith('{')
    assert len(request(f"/api/idea/{result['id']}/lineage")) == 2
try:
    request('/api/idea', {'content': 'orphan', 'parent_id': 999})
except HTTPError as error:
    assert error.code == 404
else:
    raise AssertionError('Orphan parent was accepted')
assert request('/api/stats')['total'] == 5
assert len(request('/api/mutations')) == 4
print('Candidate smoke passed: health, four real mutations, lineage, validation and stats')
