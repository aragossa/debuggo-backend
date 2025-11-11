from typing import Optional
from datetime import datetime
import uuid
from auroqa.models.client import Client, ClientCreate
from auroqa.models.user import User, UserCreate, OAuthUserInfo
from psycopg2.extras import DictCursor
from fastapi import HTTPException, status
from auroqa.Utils.auth import get_password_hash

def get_client(conn, client_id: str) -> Optional[Client]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, name, created_at, updated_at
            FROM clients WHERE id = %s
            """,
            (client_id,)
        )
        client_data = cur.fetchone()
        if client_data is None:
            return None
            
        return Client(
            id=client_data[0],
            name=client_data[1],
            created_at=client_data[2],
            updated_at=client_data[3]
        )

def create_user(conn, user_data: UserCreate) -> User:
    with conn.cursor() as cur:
        # Check if user already exists
        cur.execute("SELECT id FROM users WHERE email = %s", (user_data.email,))
        if cur.fetchone() is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # If client_id is provided, verify it exists
        if user_data.client_id:
            # Convert UUID to string before using in query
            client_id_str = str(user_data.client_id)
            cur.execute("SELECT id FROM clients WHERE id = %s", (client_id_str,))
            if cur.fetchone() is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid client_id"
                )
        
        # Create new user
        hashed_password = get_password_hash(user_data.password)
        
        # Convert client_id to string if it exists, otherwise create a new client
        if user_data.client_id:
            client_id_param = str(user_data.client_id)
        else:
            # Create a client for the new user if none provided
            client_id_param = create_client_for_user(conn, user_data.email, user_data.full_name)
        
        cur.execute(
            """
            INSERT INTO users (email, password_hash, full_name, client_id, role)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, email, full_name, is_active, created_at, last_login, client_id, role
            """,
            (user_data.email, hashed_password, user_data.full_name, client_id_param, user_data.role)
        )
        user_data = cur.fetchone()
        conn.commit()
        
        # Create default project structure for new user
        create_default_project_structure(conn, client_id_param, user_data[0])
        
        return User(
            id=user_data[0],
            email=user_data[1],
            full_name=user_data[2],
            is_active=user_data[3],
            created_at=user_data[4],
            last_login=user_data[5],
            client_id=user_data[6],
            role=user_data[7]
        )

def get_user_by_email(conn, email: str) -> Optional[User]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, email, full_name, is_active, created_at, last_login, client_id, role,
                   auth_provider, auth_provider_id, profile_picture
            FROM users WHERE email = %s
            """,
            (email,)
        )
        user_data = cur.fetchone()
        if user_data is None:
            return None
            
        return User(
            id=user_data[0],
            email=user_data[1],
            full_name=user_data[2],
            is_active=user_data[3],
            created_at=user_data[4],
            last_login=user_data[5],
            client_id=user_data[6],
            role=user_data[7],
            auth_provider=user_data[8],
            auth_provider_id=user_data[9],
            profile_picture=user_data[10]
        )

def get_or_create_oauth_user(conn, user_info: OAuthUserInfo) -> User:
    """Get an existing OAuth user or create a new one"""
    with conn.cursor() as cur:
        # Check if user already exists with this provider and provider_id
        cur.execute(
            """
            SELECT id, email, full_name, is_active, created_at, last_login, client_id, role,
                   auth_provider, auth_provider_id, profile_picture
            FROM users 
            WHERE email = %s AND auth_provider = %s
            """,
            (user_info.email, user_info.auth_provider)
        )
        user_data = cur.fetchone()
        
        if user_data is not None:
            # Update user information if needed
            cur.execute(
                """
                UPDATE users 
                SET full_name = %s, profile_picture = %s, last_login = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING id, email, full_name, is_active, created_at, last_login, client_id, role,
                          auth_provider, auth_provider_id, profile_picture
                """,
                (user_info.full_name, user_info.profile_picture, user_data[0])
            )
            updated_user = cur.fetchone()
            conn.commit()
            
            # If user doesn't have a client, create one
            if updated_user[6] is None:  # client_id is None
                client_id = create_client_for_user(conn, updated_user[1], updated_user[2])
                
                # Update user with new client_id
                cur.execute(
                    """
                    UPDATE users 
                    SET client_id = %s
                    WHERE id = %s
                    RETURNING id, email, full_name, is_active, created_at, last_login, client_id, role,
                              auth_provider, auth_provider_id, profile_picture
                    """,
                    (client_id, updated_user[0])
                )
                updated_user = cur.fetchone()
                conn.commit()
            
            return User(
                id=updated_user[0],
                email=updated_user[1],
                full_name=updated_user[2],
                is_active=updated_user[3],
                created_at=updated_user[4],
                last_login=updated_user[5],
                client_id=updated_user[6],
                role=updated_user[7],
                auth_provider=updated_user[8],
                auth_provider_id=updated_user[9],
                profile_picture=updated_user[10]
            )
        
        # Create new user
        cur.execute(
            """
            INSERT INTO users 
            (email, full_name, is_active, auth_provider, auth_provider_id, profile_picture, role)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, email, full_name, is_active, created_at, last_login, client_id, role,
                      auth_provider, auth_provider_id, profile_picture
            """,
            (user_info.email, user_info.full_name, True, 
             user_info.auth_provider, user_info.auth_provider_id, user_info.profile_picture, 'user')
        )
        new_user = cur.fetchone()
        conn.commit()
        
        # Create a client for the new user
        client_id = create_client_for_user(conn, new_user[1], new_user[2])
        
        # Update user with new client_id
        cur.execute(
            """
            UPDATE users 
            SET client_id = %s
            WHERE id = %s
            RETURNING id, email, full_name, is_active, created_at, last_login, client_id, role,
                      auth_provider, auth_provider_id, profile_picture
            """,
            (client_id, new_user[0])
        )
        updated_user = cur.fetchone()
        conn.commit()
        
        # Create default project structure for new OAuth user
        create_default_project_structure(conn, client_id, updated_user[0])
        
        return User(
            id=updated_user[0],
            email=updated_user[1],
            full_name=updated_user[2],
            is_active=updated_user[3],
            created_at=updated_user[4],
            last_login=updated_user[5],
            client_id=updated_user[6],
            role=updated_user[7],
            auth_provider=updated_user[8],
            auth_provider_id=updated_user[9],
            profile_picture=updated_user[10]
        )

def create_client_for_user(conn, email: str, full_name: str = None) -> str:
    """Create a new client for a user and return the client_id"""
    client_name = full_name or email.split('@')[0]
    client_id = str(uuid.uuid4())
    
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO clients (id, name, created_at, updated_at)
            VALUES (%s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id
            """,
            (client_id, client_name)
        )
        client_id = cur.fetchone()[0]
        conn.commit()
    
    return client_id

def create_default_project_structure(conn, client_id: str, user_id: int) -> str:
    """Create default project structure for new user"""
    with conn.cursor() as cur:
        # Create Default Project
        project_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO projects (id, name, description, client_id)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (project_id, "Default Project", "Default project for new user", client_id)
        )
        project_id = cur.fetchone()[0]
        
        # Create Default Folder (group type test case)
        cur.execute(
            """
            INSERT INTO test_cases (name, description, parent_id, type, "order", project_id, client_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            ("Default Folder", "Default folder for organizing tests", None, "group", 1, project_id, client_id)
        )
        folder_id = cur.fetchone()[0]
        
        # Create Dummy Test Case inside the folder
        cur.execute(
            """
            INSERT INTO test_cases (name, description, parent_id, type, "order", project_id, client_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            ("Sample Test Case", "This is a sample test case to get you started", folder_id, "test", 1, project_id, client_id)
        )
        test_case_id = cur.fetchone()[0]
        
        # Create sample test steps for the dummy test
        sample_steps = [
            {
                'action': 'navigate',
                'element_path': 'https://example.com',
                'value': '',
                'description': 'Navigate to example website'
            },
            {
                'action': 'wait',
                'element_path': '',
                'value': '2',
                'description': 'Wait for page to load'
            },
            {
                'action': 'assert',
                'element_path': 'title',
                'value': 'Example Domain',
                'description': 'Verify page title'
            }
        ]
        
        for i, step in enumerate(sample_steps, 1):
            cur.execute(
                """
                INSERT INTO test_steps (test_case_id, step_order, action, element_path, value, description)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (test_case_id, i, step['action'], step['element_path'], step['value'], step['description'])
            )
        
        conn.commit()
        return project_id

def get_client_test_cases(conn, client_id: str):
    with conn.cursor(cursor_factory=DictCursor) as cur:
        cur.execute(
            """
            SELECT id, name, description, parent_id, type, order, 
                   created_at, updated_at, test_case_id, curl, python_script
            FROM test_cases 
            WHERE client_id = %s
            """,
            (client_id,)
        )
        return cur.fetchall()
