from ntpath import exists
from fastapi import FastAPI, HTTPException, File, UploadFile, Form, Depends
from requests import delete
from app.schemas import UserCreate, UserRead, UserUpdate
from app.db import Post, create_db_and_tables, get_async_session, User
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager
from sqlalchemy import Select
from app.images import imagekit
from imagekitio.models.UploadFileRequestOptions import UploadFileRequestOptions
import os, tempfile, shutil
import uuid
from app.users import current_active_user, auth_backend, fastapi_users 

@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_db_and_tables()
    yield

app = FastAPI(lifespan=lifespan)

app.include_router(fastapi_users.get_auth_router(auth_backend), prefix="/auth/jwt", tags=["auth"])
app.include_router(fastapi_users.get_register_router(UserRead, UserCreate), prefix="/auth", tags=["auth"])
app.include_router(fastapi_users.get_reset_password_router(), prefix="/auth", tags=["auth"])
app.include_router(fastapi_users.get_verify_router(UserRead), prefix="/auth", tags=["auth"])
app.include_router(fastapi_users.get_users_router(UserRead, UserUpdate), prefix="/users", tags=["users"])



# Upload a post
@app.post('/posts')
async def upload_post(
    user: User = Depends(current_active_user),
    file: UploadFile = File(...),
    caption: str = Form(...),
    session: AsyncSession = Depends(get_async_session)
):
  
  temp_file_path = None

  try:

    # Handle the case where filename might be None
    file_extension = ""
    if file.filename:
        file_extension = os.path.splitext(file.filename)[1]
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
        temp_file_path = temp_file.name
        shutil.copyfileobj(file.file, temp_file)

    upload_result = imagekit.upload_file(
        file=open(temp_file_path,'rb'),
        file_name=file.filename,
        options=UploadFileRequestOptions(
            use_unique_file_name=True,
            folder="/uploads/",
            tags=["backend-upload"]
        )   
    )

    # Check if upload was successful by verifying we got a URL back
    if hasattr(upload_result, 'url') and upload_result.url:
        post = Post(
            user_id=user.id,
            caption=caption,
            url=upload_result.url,
            file_type="video" if file.content_type and file.content_type.startswith("video/") else "image",
            file_name=upload_result.name
        )
        session.add(post)
        await session.commit()
        await session.refresh(post)
        return {"message": "Post uploaded successfully", "post": post}
  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e)) from e
  finally:
    if temp_file_path and os.path.exists(temp_file_path):
        os.unlink(temp_file_path)
    file.file.close()



# Get feed
@app.get('/posts')
async def get_feed(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
  result = await session.execute(Select(Post).order_by(Post.created_at.desc()))
  posts = [row[0] for row in result.all()]

  posts_data = []
  for post in posts:
    posts_data.append(
        {
            "id": str(post.id),
            "user_id": str(post.user_id),
            "caption": post.caption,
            "url": post.url,
            "file_type": post.file_type,
            "file_name": post.file_name,
            "created_at": post.created_at.isoformat(),
            "updated_at": post.updated_at.isoformat() if post.updated_at else None,
            "is_owner": str(post.user_id) == str(user.id),
            "email": user.email,
        }
    )
  return {"posts": posts_data}

   

# Delete a post
@app.delete('/posts/{post_id}')
async def delete_post(post_id: str, user: User = Depends(current_active_user), session: AsyncSession = Depends(get_async_session)):
    try:
        post_uuid = uuid.UUID(post_id)
        result = await session.execute(Select(Post).where(Post.id == post_uuid))
        post = result.scalars().first()

        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        if post.user_id != user.id:
            raise HTTPException(status_code=403, detail="You do not have permission to delete this post")
        
        # Delete the file from ImageKit first
        try:
            # Extract file ID from the URL
            if post.file_name:
                delete_response = imagekit.delete_file(file_id=post.file_name)
                # Handle ResponseMetadataResult safely using getattr
                response_data = getattr(delete_response, 'response', None)
                if response_data is not None:
                    if isinstance(response_data, dict):
                        if not response_data.get('success', True):  # Assume success if not specified
                            error_message = response_data.get('message', 'Unknown error')
                            print(f"Failed to delete file from ImageKit: {error_message}")
                    else:
                        # If response is not a dict, try to convert it or handle accordingly
                        print(f"Delete response: {response_data}")
                else:
                    # Handle case where there's no response attribute
                    print(f"Delete operation completed: {delete_response}")
        except Exception as imagekit_error:
            # Log the error but don't stop the post deletion
            print(f"Failed to delete file from ImageKit: {imagekit_error}")
        
        # Delete the post from the database
        await session.delete(post)
        await session.commit()
        return {"message": "Post deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    
