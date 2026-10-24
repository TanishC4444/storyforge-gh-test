"""Minimal GitHub REST client, authenticated with the caller's own token.

The token is held only for the lifetime of one API request. It is never logged,
cached or written to disk.
"""
from __future__ import annotations

from typing import Any

import httpx


class GitHubError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class GitHubClient:
    def __init__(self, token: str, repo: str, api: str = 'https://api.github.com', transport: httpx.BaseTransport | None = None):
        self.repo = repo
        # httpx drops the Authorization header when an artifact download redirects
        # to GitHub's blob storage, so the token never leaves api.github.com.
        self.http = httpx.Client(
            base_url=api,
            headers={
                'Authorization': f'Bearer {token}',
                'Accept': 'application/vnd.github+json',
                'X-GitHub-Api-Version': '2022-11-28',
                'User-Agent': 'storyforge-api',
            },
            timeout=30.0,
            follow_redirects=True,
            transport=transport,
        )

    def close(self):
        self.http.close()

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = self.http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise GitHubError(502, f'GitHub request failed: {type(exc).__name__}') from None
        if response.status_code >= 400:
            try:
                payload=response.json()
                message=payload.get('message', 'Upstream request failed') if isinstance(payload,dict) else 'Upstream request failed'
            except ValueError:
                message = response.text
            token=self.http.headers.get('Authorization','').removeprefix('Bearer ')
            message=str(message).replace(token,'[redacted]') if token else str(message)
            raise GitHubError(response.status_code, f'GitHub: {message[:500]}')
        return response

    def get(self, path: str, **params) -> Any:
        response=self._request('GET', path, params=params or None)
        try:return response.json()
        except ValueError:raise GitHubError(502,'GitHub returned invalid JSON') from None

    def repo_path(self, suffix: str) -> str:
        return f'/repos/{self.repo}/{suffix}'

    # Identity and permissions

    def user(self) -> dict:
        return self.get('/user')

    def repository(self) -> dict:
        return self.get(self.repo_path('').rstrip('/'))

    # Runs

    def workflow_runs(self, workflow: str, per_page: int = 20) -> list[dict]:
        data = self.get(self.repo_path(f'actions/workflows/{workflow}/runs'), per_page=per_page, event='workflow_dispatch')
        return data['workflow_runs']

    def run(self, run_id: int) -> dict:
        return self.get(self.repo_path(f'actions/runs/{run_id}'))

    def jobs(self, run_id: int) -> list[dict]:
        jobs, page = [], 1
        while True:
            data = self.get(self.repo_path(f'actions/runs/{run_id}/jobs'), filter='latest', per_page=100, page=page)
            jobs += data['jobs']
            if len(jobs) >= data['total_count'] or not data['jobs']:
                return jobs
            page += 1

    def artifacts(self, run_id: int) -> list[dict]:
        items, page = [], 1
        while True:
            data = self.get(self.repo_path(f'actions/runs/{run_id}/artifacts'), per_page=100, page=page)
            items += data['artifacts']
            if len(items) >= data['total_count'] or not data['artifacts']:
                return items
            page += 1

    def artifact_zip(self, artifact_id: int) -> bytes:
        return self._request('GET', self.repo_path(f'actions/artifacts/{artifact_id}/zip')).content

    def dispatch(self, workflow: str, ref: str, inputs: dict[str, str]) -> int | None:
        """Start a workflow. Returns the new run ID when GitHub reports it, else None."""
        path = self.repo_path(f'actions/workflows/{workflow}/dispatches')
        body = {'ref': ref, 'inputs': inputs}
        try:
            response = self._request('POST', path, json={**body, 'return_run_details': True})
        except GitHubError as exc:
            # Older API versions reject the run-details flag; dispatch without it.
            if exc.status != 422 or 'return_run_details' not in exc.message:
                raise
            response = self._request('POST', path, json=body)
        if response.status_code == 200 and response.content:
            return response.json().get('workflow_run_id')
        return None

    def cancel(self, run_id: int) -> None:
        self._request('POST', self.repo_path(f'actions/runs/{run_id}/cancel'))
