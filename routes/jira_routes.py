from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional, Dict
from auroqa.Services.JiraService import JiraService
from auroqa.Utils.Connectors.db_utils import get_db_connection_context
from auroqa.models.user import User
from auroqa.dependencies import get_current_user
# Better to pass get_current_user as dependency if possible, or duplicate logic/import from localized auth utils.
# Checking main.py: get_current_user is defined in main.py. It's not in a shared module.
# I might need to move get_current_user to a shared module or pass it.
# Check auroqa/Utils/auth.py or similar.
# main.py lines 225 defines get_current_user. 
# It depends on oauth2_scheme which is also in main.py.
# This is a common pattern issue. 
# I will check if any other route uses get_current_user. 
# auroqa/api/suite_endpoints.py uses set_get_current_user pattern.
# I should use the same pattern.

router = APIRouter()


class JiraCredentials(BaseModel):
    url: str
    email: str
    token: str

class JiraSearchRequest(JiraCredentials):
    jql: Optional[str] = None
    project_key: Optional[str] = None
    priority: Optional[str] = None

class JiraImportRequest(JiraCredentials):
    issues: List[Dict]
    project_id: str
    group_id: Optional[int] = None

@router.post("/jira/item/connect")
async def connect_jira(creds: JiraCredentials): # Using different path to avoid conflicts? /jira/connect
    try:
        service = JiraService(creds.url, creds.email, creds.token) # Constructor connects
        return {"status": "success", "message": "Connected to Jira"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/jira/projects")
async def get_projects(creds: JiraCredentials):
    try:
        service = JiraService(creds.url, creds.email, creds.token)
        return service.get_projects()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/jira/priorities")
async def get_priorities(creds: JiraCredentials):
    try:
        service = JiraService(creds.url, creds.email, creds.token)
        return service.get_priorities()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/jira/search")
async def search_issues(req: JiraSearchRequest):
    try:
        service = JiraService(req.url, req.email, req.token)
        jql = req.jql
        if not jql:
            parts = []
            if req.project_key:
                parts.append(f'project = "{req.project_key}"')
            if req.priority:
                parts.append(f'priority = "{req.priority}"')
            jql = " AND ".join(parts) if parts else ""
        
        if not jql:
             raise HTTPException(status_code=400, detail="Either JQL or Project/Priority must be provided")

        return service.search_issues(jql)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/jira/import")
async def import_issues(req: JiraImportRequest, user: User = Depends(get_current_user)):
    if not user.client_id:
         raise HTTPException(status_code=400, detail="User has no client associated")

    try:
        with get_db_connection_context() as conn:
            with conn.cursor() as cur:
                imported_ids = []
                for issue in req.issues:
                    # Mapping: Summary -> Name, Description -> Description
                    name = f"[{issue.get('key')}] {issue.get('summary')}"
                    description = issue.get('description')
                    
                    # Handle Jira Cloud ADF (Atlassian Document Format) which is a dict
                    if isinstance(description, (dict, list)):
                        import json
                        description = json.dumps(description)
                    elif description is None:
                        description = ""
                    else:
                        description = str(description)
                    
                    cur.execute(
                        """
                        INSERT INTO test_cases (name, description, parent_id, type, "order", project_id, client_id, test_type)
                        VALUES (%s, %s, %s, 'test', 
                            (SELECT COALESCE(MAX("order"), 0) + 1 FROM test_cases WHERE parent_id IS NOT DISTINCT FROM %s),
                            %s, %s, 'ui')
                        RETURNING id
                        """,
                        (name, description, req.group_id, req.group_id, req.project_id, str(user.client_id))
                    )
                    imported_ids.append(cur.fetchone()[0])
                
                conn.commit()
                return {"imported_count": len(imported_ids), "ids": imported_ids}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
