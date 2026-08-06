#!/usr/bin/env python3
"""Minimal smoke test for the independent free roster server."""
import json
import os
import sys
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

BASE_URL = os.environ.get('VO_SMOKE_URL', 'http://127.0.0.1:8092').rstrip('/')
EXPECTED_IDS = {'main', '2', 'team', 'dising', 'memory', 'worker', 'designer'}
OPENER = build_opener(ProxyHandler({}))


def request(path, method='GET'):
    req = Request(BASE_URL + path, method=method, headers={'Origin': 'https://smoke.test'})
    try:
        response = OPENER.open(req, timeout=5)
    except HTTPError as exc:
        response = exc
    return response, response.read()


def main():
    health_response, health_body = request('/health')
    health = json.loads(health_body)
    assert health_response.status == 200 and health['ok'], health

    for endpoint in ('/api/agents', '/api/roster'):
        response, body = request(endpoint)
        data = json.loads(body)
        assert response.status == 200, (endpoint, response.status, data)
        assert response.headers.get('Access-Control-Allow-Origin') == '*', endpoint
        agents = data['agents']
        ids = {agent['id'] for agent in agents}
        assert ids == EXPECTED_IDS, (endpoint, sorted(ids))
        missing_models = [agent['id'] for agent in agents if not agent.get('model')]
        assert not missing_models, (endpoint, missing_models)

    response, body = request('/')
    assert response.status == 200 and b'My Virtual Office' in body
    assert response.headers.get_content_type() == 'text/html'

    response, body = request('/missing')
    assert response.status == 404 and json.loads(body)['error'] == 'not_found'

    response, _ = request('/api/roster', method='OPTIONS')
    assert response.status == 204
    assert response.headers.get('Access-Control-Allow-Origin') == '*'
    assert response.headers.get('Access-Control-Allow-Methods') == 'GET, OPTIONS'

    print('PASS: health, roster APIs, 7 agents/models, static HTML, CORS, and JSON 404')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        raise
