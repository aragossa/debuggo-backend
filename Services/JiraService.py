import logging
from jira import JIRA
from typing import List, Dict, Optional


logger = logging.getLogger(__name__)

class JiraService:
    def __init__(self, url: str, email: str, token: str):
        self.url = url
        self.email = email
        self.token = token
        self.jira = None
        self.connect()

    def connect(self):
        try:
            self.jira = JIRA(
                server=self.url,
                basic_auth=(self.email, self.token),
                options={"server": self.url, "rest_api_version": "3"}
            )
            logger.info(f"Connected to Jira at {self.url}")
        except Exception as e:
            logger.error(f"Failed to connect to Jira: {e}")
            raise Exception(f"Failed to connect to Jira: {str(e)}")

    def get_projects(self) -> List[Dict]:
        if not self.jira:
            self.connect()
        try:
            projects = self.jira.projects()
            return [{'id': p.id, 'key': p.key, 'name': p.name} for p in projects]
        except Exception as e:
            logger.error(f"Error fetching projects: {e}")
            raise

    def get_priorities(self) -> List[Dict]:
        if not self.jira:
            self.connect()
        try:
            priorities = self.jira.priorities()
            return [{'id': p.id, 'name': p.name} for p in priorities]
        except Exception as e:
            logger.error(f"Error fetching priorities: {e}")
            raise

    def search_issues(self, jql: str, max_results: int = 50) -> List[Dict]:
        if not self.jira:
            self.connect()
        try:
            # Error message said: migrate to /rest/api/3/search/jql
            resource_path = "rest/api/3/search"
            
            # Use 'strict' validation to catch errors, but 'warn' is safer?
            # Actually, let's look at the payload structure for 'search' vs 'search/jql'.
            # It seems the library might be doing something behind the scenes.
            # Let's try to use the raw session to hit /rest/api/3/search directly
            # IF that failed with 410, then we MUST use /rest/api/3/search/jql
            # Let's try /rest/api/3/search/jql AGAIN with minimal payload.
            
            resource_path = "rest/api/3/search"
            
            # NOTE: Atlassian docs say POST /rest/api/3/search is deprecated.
            # We must use POST /rest/api/3/search/jql? No wait, is it?
            # Actually, let's try to use the library's `search_issues` but force it to use API v3?
            # I already did that with `rest_api_version="3"`.
            # If that failed, I have to manuall call.
            
            # Let's try /rest/api/3/search with a simpler payload, removing 'validateQuery'.
            # Maybe the 410 was due to 'validateQuery' being deprecated?
            # No, "The requested API has been removed" usually means the endpoint path itself.
            
            # Let's try the path: `rest/api/3/search` again?
            # User log said: `POST /rest/api/3/search` -> 400.
            # Wait, user log said `POST /rest/api/3/search/jql` -> 400 "Invalid request payload".
            # User log said `POST /rest/api/3/search` -> 410 "API removed".
            
            # OK, so `/rest/api/3/search` is DEAD.
            # `/rest/api/3/search/jql` is ALIVE but my payload was wrong.
            # Payload I used for `search/jql`: {"jql": ..., "maxResults": ..., "fields": ..., "validation": "strict"}
            # Maybe `validation` key is wrong? Or `fields`?
            # Let's try minimal payload for `search/jql`.
            
            resource_path = "rest/api/3/search/jql"
            payload = {
                "jql": jql,
                "maxResults": max_results,
                "fields": ["summary", "description", "status", "priority", "issuelinks"]
            }
            # validation/validateQuery might be query param, not body param for this new endpoint?
            
            response = self.jira._session.post(
                url=f"{self.url}/{resource_path}",
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            issues = data.get('issues', [])

            return [
                {
                    'id': issue.get('id'),
                    'key': issue.get('key'),
                    'summary': issue.get('fields', {}).get('summary'),
                    'description': issue.get('fields', {}).get('description'),
                    'status': issue.get('fields', {}).get('status', {}).get('name'),
                    'priority': issue.get('fields', {}).get('priority', {}).get('name', 'None')
                }
                for issue in issues
            ]
        except Exception as e:
            logger.error(f"Error searching issues with JQL '{jql}': {e}")
            raise
