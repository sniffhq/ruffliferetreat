"""
jira_service.py - Mirrors staff support tickets into Jira (sniffhq.atlassian.net).
Requires JIRA_EMAIL and JIRA_API_TOKEN to be set in .env — generate an API
token at https://id.atlassian.com/manage-profile/security/api-tokens.
"""

import logging
import requests
from flask import current_app

logger = logging.getLogger(__name__)


def _paragraph(text):
    return {'type': 'paragraph', 'content': [{'type': 'text', 'text': text}]}


def create_support_ticket_issue(ticket):
    """
    Create a Jira issue for a SupportTicket. Returns (issue_key, issue_url).
    Raises on failure — callers should catch and log rather than let a Jira
    outage block ticket submission.
    """
    base_url   = current_app.config.get('JIRA_BASE_URL')
    email      = current_app.config.get('JIRA_EMAIL')
    token      = current_app.config.get('JIRA_API_TOKEN')
    project    = current_app.config.get('JIRA_PROJECT_KEY', 'SUPP')
    issue_type = current_app.config.get('JIRA_ISSUE_TYPE', 'Task')

    if not all([base_url, email, token]):
        raise RuntimeError('Jira is not configured — set JIRA_EMAIL and JIRA_API_TOKEN in .env.')

    submitter  = ticket.submitter
    who        = f'{submitter.first_name} {submitter.last_name}' if submitter else 'Unknown staff member'
    who_email  = submitter.email if submitter and submitter.email else 'no email on file'

    description_doc = {
        'type': 'doc',
        'version': 1,
        'content': [
            _paragraph(ticket.description),
            _paragraph(f'Submitted by: {who} ({who_email})'),
            _paragraph(f'Ticket type: {ticket.type_label}'),
            _paragraph(f'Internal ticket: rufflife.app/admin/support/{ticket.id}'),
        ],
    }

    payload = {
        'fields': {
            'project':     {'key': project},
            'summary':     f'[Ruff Life #{ticket.id}] {ticket.subject}',
            'description': description_doc,
            'issuetype':   {'name': issue_type},
            'labels':      ['ruff-life-retreat', ticket.ticket_type],
        }
    }

    resp = requests.post(
        f'{base_url.rstrip("/")}/rest/api/3/issue',
        json=payload,
        auth=(email, token),
        headers={'Accept': 'application/json'},
        timeout=10,
    )
    resp.raise_for_status()
    issue_key = resp.json()['key']
    issue_url = f'{base_url.rstrip("/")}/browse/{issue_key}'
    return issue_key, issue_url
