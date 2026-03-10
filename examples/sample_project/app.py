"""
Sample FastAPI e-commerce app — 5 files for BlastShield demo testing.
File 1: app.py — Main application entry point.
"""
from fastapi import FastAPI
from models import Order, User
from routes import router
from db import database

app = FastAPI(title="MiniShop API")
app.include_router(router)

orders = []
users = []


@app.get("/health")
def health_check():
    return {"status": "ok", "version": "0.1.0"}


@app.post("/register")
def register_user(user: dict):
    users.append(user)
    return {"id": len(users), "name": user.get("name")}

# Documented code

# Documented code
