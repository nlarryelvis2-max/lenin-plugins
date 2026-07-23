#!/usr/bin/env python3
"""Dependency-free stdio MCP for Lenin owner and administrator accounts."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from owner_client import request

TOOLS = [
    {
        "name": "lenin_owner_overview",
        "description": "List Lenin users, projects and current project grants. Administrator access only.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "lenin_owner_user_create",
        "description": "Create one permanent participant account without project access. Returns its one-time temporary password.",
        "inputSchema": {
            "type": "object",
            "required": ["login", "name", "confirmed"],
            "properties": {
                "login": {"type": "string"},
                "name": {"type": "string"},
                "confirmed": {"type": "boolean", "description": "Must be true after owner confirms account creation."},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "lenin_owner_project_access_set",
        "description": "Grant or update a user's access to one project.",
        "inputSchema": {
            "type": "object",
            "required": ["login", "project_id", "role", "confirmed"],
            "properties": {
                "login": {"type": "string"},
                "project_id": {"type": "string"},
                "role": {"type": "string", "enum": ["viewer", "contributor", "project-owner"]},
                "confirmed": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "lenin_owner_project_access_remove",
        "description": "Remove a user's access to one project.",
        "inputSchema": {
            "type": "object",
            "required": ["login", "project_id", "confirmed"],
            "properties": {
                "login": {"type": "string"},
                "project_id": {"type": "string"},
                "confirmed": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "lenin_owner_users_bootstrap",
        "description": "Create multiple permanent participant accounts without projects and write credentials to a local mode-0600 TSV file. Existing logins are skipped and never reset.",
        "inputSchema": {
            "type": "object",
            "required": ["users", "output_path", "confirmed"],
            "properties": {
                "users": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["login", "name"],
                        "properties": {"login": {"type": "string"}, "name": {"type": "string"}},
                        "additionalProperties": False,
                    },
                },
                "output_path": {"type": "string", "description": "Absolute local .tsv path."},
                "confirmed": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
]


def call(name: str, args: dict) -> dict:
    if name == "lenin_owner_overview":
        return request("/api/admin/overview")
    if not args.get("confirmed"):
        raise ValueError("Операция меняет доступы: передайте confirmed=true после подтверждения владельца.")
    if name == "lenin_owner_user_create":
        return request("/api/admin/users", method="POST", body={
            "id": args.get("login"), "name": args.get("name"), "role": "participant", "projectIds": [],
        })
    if name == "lenin_owner_project_access_set":
        login, project = args.get("login"), args.get("project_id")
        return request(f"/api/admin/users/{login}/projects/{project}", method="PUT", body={"role": args.get("role")})
    if name == "lenin_owner_project_access_remove":
        login, project = args.get("login"), args.get("project_id")
        return request(f"/api/admin/users/{login}/projects/{project}", method="DELETE")
    if name == "lenin_owner_users_bootstrap":
        return bootstrap(args)
    raise ValueError(f"Неизвестный инструмент: {name}")


def bootstrap(args: dict) -> dict:
    output = Path(str(args.get("output_path") or ""))
    if not output.is_absolute() or output.suffix.lower() != ".tsv":
        raise ValueError("output_path должен быть абсолютным путём к .tsv")
    overview = request("/api/admin/overview")
    existing = {item["id"] for item in overview.get("users", [])}
    skipped, created_count = [], 0
    output.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write("login\tname\ttemporary_password\n")
        stream.flush()
        os.fsync(stream.fileno())
        for item in args.get("users") or []:
            login, name = str(item.get("login") or "").strip(), str(item.get("name") or "").strip()
            if login in existing:
                skipped.append(login)
                continue
            created = request("/api/admin/users", method="POST", body={
                "id": login, "name": name, "role": "participant", "projectIds": [],
            })
            safe_name = name.replace("\t", " ").replace("\r", " ").replace("\n", " ")
            stream.write(f"{login}\t{safe_name}\t{created.get('temporaryPassword', '')}\n")
            stream.flush()
            os.fsync(stream.fileno())
            created_count += 1
            existing.add(login)
    return {"created": created_count, "skipped_existing": skipped, "credentials_file": str(output)}


def send(value: dict) -> None:
    sys.stdout.write(json.dumps(value, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> None:
    for line in sys.stdin:
        message = {}
        try:
            message = json.loads(line)
            request_id = message.get("id")
            method = message.get("method")
            if method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "lenin-owner", "version": "0.1.0"},
                }
            elif method == "notifications/initialized":
                continue
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                params = message.get("params") or {}
                payload = call(str(params.get("name") or ""), params.get("arguments") or {})
                result = {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]}
            else:
                raise ValueError(f"Метод не поддерживается: {method}")
            if request_id is not None:
                send({"jsonrpc": "2.0", "id": request_id, "result": result})
        except Exception as error:
            if message.get("id") is not None:
                send({"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32000, "message": str(error)}})


if __name__ == "__main__":
    main()
