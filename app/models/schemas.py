from pydantic import BaseModel
from typing import List, Optional, Any

class WhatsAppMessage(BaseModel):
    from_number: str
    text: str
    message_id: str

class PropertyResponse(BaseModel):
    id: int
    title: str
    price: float
    description: str

class SpringBootResponse(BaseModel):
    status: str
    data: Optional[Any] = None
