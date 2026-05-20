import os

new_endpoints = """

@router.get("/admin/api/clients/{client_id}")
async def admin_api_get_client(
    client_id: int,
    actor: str = Depends(verify_admin_api_key),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    # Return full data needed for edit forms and keys
    data = client_to_api_dict(client)
    data["access_token"] = client.access_token
    data["portal_key"] = client.portal_key
    data["public_key"] = getattr(client, "public_key", None)
    return {"status": "success", "client": data}


@router.post("/admin/api/clients/{client_id}/keys/rotate")
async def admin_api_rotate_key(
    client_id: int,
    request: Request,
    payload: dict,
    actor: str = Depends(verify_admin_api_key),
    db: AsyncSession = Depends(get_db),
):
    key_type = payload.get("key_type")
    if key_type not in ["api_key", "portal_key", "public_key"]:
        raise HTTPException(status_code=400, detail="Invalid key type")
        
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    old_key = client.api_key
    if key_type == "api_key":
        client.api_key = secrets.token_urlsafe(32)
        clear_client_cache(old_key)
    elif key_type == "portal_key":
        client.portal_key = secrets.token_urlsafe(16)
    elif key_type == "public_key" and hasattr(client, "public_key"):
        client.public_key = secrets.token_hex(16)
        
    await log_admin_action(db, request, actor, f"client.{key_type}_rotated", client.id, f"{key_type} rotated via admin API")
    await db.commit()
    await db.refresh(client)
    return {"status": "success", "key_type": key_type, "new_value": getattr(client, key_type)}


@router.delete("/admin/api/clients/{client_id}")
async def admin_api_delete_client(
    client_id: int,
    request: Request,
    actor: str = Depends(verify_admin_api_key),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    client_name = client.name
    client_api_key = client.api_key

    # Delete client 
    await db.delete(client)
    clear_client_cache(client_api_key)
    
    await log_admin_action(db, request, actor, "client.deleted", client_id, f"Client {client_name} deleted via API")
    await db.commit()
    return {"status": "success", "message": f"Client {client_name} deleted"}

"""

with open('app/routers/admin.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Insert before "─── ROUTES"
target = "# ─── ROUTES"
if target in content:
    content = content.replace(target, new_endpoints + "\n" + target)
    with open('app/routers/admin.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("SUCCESS: Added new JSON API endpoints for Vercel")
else:
    print("ERROR: Could not find ROUTES section")
