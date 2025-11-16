from pydantic import BaseModel

class TextPost(BaseModel):
    title: str
    content: str