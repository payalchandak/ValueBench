from pydantic import BaseModel
from all_the_llms import LLM
from dotenv import load_dotenv

load_dotenv()

class User(BaseModel):
    name: str
    age: int

llm = LLM("gpt-4o")
user = llm.structured_completion(
    messages=[{"role": "user", "content": "Jason is 25 years old"}],
    response_model=User
)
print(user.name, user.age)