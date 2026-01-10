from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from auroqa.models.user import User
from auroqa.Utils.auth import SECRET_KEY, ALGORITHM
from auroqa.Utils.Connectors.db_utils import get_db_connection_context
from auroqa.models.crud import get_user_by_email

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login")

async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    with get_db_connection_context() as conn:
        # Debug logging
        if conn.closed:
            raise HTTPException(status_code=500, detail="Database connection error")
        
        user = get_user_by_email(conn, email)
        if user is None:
            raise credentials_exception
        return user
