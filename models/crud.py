from typing import Optional
from datetime import datetime
from models.client import Client, ClientCreate
from models.user import User, UserCreate
from psycopg2.extras import DictCursor
from fastapi import HTTPException, status
from Utils.auth import get_password_hash

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
            cur.execute("SELECT id FROM clients WHERE id = %s", (user_data.client_id,))
            if cur.fetchone() is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid client_id"
                )
        
        # Create new user
        hashed_password = get_password_hash(user_data.password)
        cur.execute(
            """
            INSERT INTO users (email, password_hash, full_name, client_id, role)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, email, full_name, is_active, created_at, last_login, client_id, role
            """,
            (user_data.email, hashed_password, user_data.full_name, user_data.client_id, user_data.role)
        )
        user_data = cur.fetchone()
        conn.commit()
        
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
            SELECT id, email, full_name, is_active, created_at, last_login, client_id, role
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
            role=user_data[7]
        )

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
