# main.py
from fastapi import FastAPI

app = FastAPI()

@app.get("/err")
def err():
    return "QY"
