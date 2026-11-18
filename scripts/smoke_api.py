#!/usr/bin/env python3
"""Exercise a candidate on loopback, with a disposable database only."""
import json
import sys
import subprocess
from pathlib import Path
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
MUTATIONS = ['expand', 'rephrase', 'mutate_keywords', 'synthesize', 'question', 'twist', 'headline', 'flip']
seed = request('/api/idea', {'content': 'Deploy check: Grădină 🌱 "quotes" C:\\notes\nline'})
preview = request(f"/api/idea/{seed['id']}/preview")
assert [row['mutation'] for row in preview['results']] == MUTATIONS
assert all(row['content'] and row['existing_id'] is None for row in preview['results'])
draft = request('/api/preview', {'content': 'Build a calmer internet'})
assert {row['mutation']: row['content'] for row in draft['results']}['question'] == 'What if we build a calmer internet?'
for mutation in MUTATIONS:
    result = request('/api/idea', {'parent_id': seed['id'], 'mutation': mutation})
    assert result['parent_id'] == seed['id'] and result['depth'] == 1
    assert result['content'] and not result['content'].startswith('{')
    assert result['content'] == {row['mutation']: row['content'] for row in preview['results']}[mutation]
    assert len(request(f"/api/idea/{result['id']}/lineage")) == 2
assert request('/api/idea', {'parent_id': seed['id'], 'mutation': 'expand'})['parent_id'] == seed['id']
for rejected in [{'content': 'visit www.spam.example'}, {'content': 'x\u202ey'}]:
    try:
        request('/api/idea', rejected)
    except HTTPError as error:
        assert error.code == 422
    else:
        raise AssertionError('Text policy accepted an invalid idea')
TOTAL = 1 + len(MUTATIONS)
assert request(f"/api/idea/{seed['id']}/water", {})['counted'] is True
assert request(f"/api/idea/{seed['id']}/water", {}) == {'idea_id': seed['id'], 'water': 1, 'counted': False}
sections = request('/api/discover')
assert sections['branching'][0]['id'] == seed['id'] and sections['branching'][0]['children'] == len(MUTATIONS)
assert sections['trending'][0]['id'] == seed['id'] and sections['trending'][0]['water'] == 1
assert len(request('/api/idea?leaves_only=true')) == len(MUTATIONS)
assert request('/api/random')['root_id'] == seed['id']
assert request('/api/stats')['water'] == 1
try:
    request('/api/idea', {'content': 'orphan', 'parent_id': 999})
except HTTPError as error:
    assert error.code == 404
else:
    raise AssertionError('Orphan parent was accepted')
assert request('/api/stats')['total'] == TOTAL
assert [row['id'] for row in request('/api/mutations')] == MUTATIONS
# Operator tests are restricted to this candidate's disposable database.
database = Path(sys.argv[3]).resolve()
assert database.parent.name.startswith('unison-deploy-verify.') and database.parent.parent == Path('/tmp')
assert database.name == 'evolution.db'
operator = Path(__file__).resolve().with_name('moderate.py')

def moderate(*args):
    result = subprocess.run([sys.executable, str(operator), '--db', str(database), *args], capture_output=True, text=True, timeout=8, check=True)
    return json.loads(result.stdout)

for _ in range(2):
    assert request(f"/api/idea/{seed['id']}/report", {'reason': 'privacy'}) == {'status': 'received'}
assert len(moderate('queue')) == 1
assert moderate('hide', str(seed['id']), '--reason', 'privacy')['affected'] == TOTAL
assert request('/api/idea') == []
assert request('/api/stats')['total'] == 0
assert all(rows == [] for rows in request('/api/discover').values())
for path in [f"/api/idea/{seed['id']}", f"/api/idea/{result['id']}/lineage"]:
    try:
        request(path)
    except HTTPError as error:
        assert error.code == 404
    else:
        raise AssertionError('Hidden content was publicly readable')
assert moderate('restore', str(seed['id']))['affected'] == TOTAL
assert request('/api/stats')['total'] == TOTAL
assert request('/api/stats')['board_revision'] == 2
assert request(f"/api/idea/{seed['id']}")['content'] == seed['content']
assert moderate('queue') == []
print('Candidate smoke passed: real mutations, reports, private operator hide/restore, visibility and preservation')
