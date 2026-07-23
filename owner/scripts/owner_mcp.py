#!/usr/bin/env python3
"""Dependency-free stdio MCP for Lenin owner accounts."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import quote, urlencode

from owner_client import request

TOOLS = [
    {
        "name": "lenin_owner_overview",
        "description": "List Lenin users, projects and current project grants. Global owner access only.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "lenin_owner_user_list",
        "description": "Return a compact filterable user directory with login, role, status, password state, project grants and Uplink connection state.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Optional case-insensitive login or name search."},
                "role": {"type": "string", "enum": ["owner", "admin", "participant", "guest"]},
                "status": {"type": "string", "enum": ["active", "disabled"]},
                "project_id": {"type": "string"},
                "uplink_state": {
                    "type": "string",
                    "enum": ["connected", "stale", "pending", "setup_issued", "revoked", "not_connected", "unavailable"],
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "lenin_owner_user_inspect",
        "description": "Inspect one user's public account state, effective access summary and Uplink connection metadata without reading private content.",
        "inputSchema": {
            "type": "object",
            "required": ["login"],
            "properties": {"login": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "lenin_owner_user_context_read",
        "description": "Read one user's canonical personal context and knowledge inventory. The stated reason is written to the administrator audit.",
        "inputSchema": {
            "type": "object",
            "required": ["login", "reason"],
            "properties": {
                "login": {"type": "string"},
                "reason": {"type": "string", "description": "Short operational reason for this sensitive read."},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "lenin_owner_user_conversation_read",
        "description": "Read a bounded page of one user's project-scoped Lenin conversation. The stated reason is written to the administrator audit.",
        "inputSchema": {
            "type": "object",
            "required": ["login", "project_id", "reason"],
            "properties": {
                "login": {"type": "string"},
                "project_id": {"type": "string"},
                "reason": {"type": "string", "description": "Short operational reason for this sensitive read."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50},
                "offset": {"type": "integer", "minimum": 0, "default": 0},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "lenin_owner_user_history_read",
        "description": "Read one user's recent Lenin interaction history across every project. The reason is written to the administrator audit.",
        "inputSchema": {
            "type": "object",
            "required": ["login", "reason"],
            "properties": {
                "login": {"type": "string"},
                "reason": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 100},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "lenin_owner_user_uplink_summary",
        "description": "Read aggregate Uplink connection and inventory state for one user. Never returns raw paths, filenames, session text or downloads.",
        "inputSchema": {
            "type": "object",
            "required": ["login", "reason"],
            "properties": {
                "login": {"type": "string"},
                "reason": {"type": "string", "description": "Short operational reason for this sensitive read."},
            },
            "additionalProperties": False,
        },
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
        "name": "lenin_owner_project_create",
        "description": "Create a project and optionally allocate one active user as the person responsible for its result.",
        "inputSchema": {
            "type": "object",
            "required": ["name", "confirmed"],
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "company": {"type": "string"},
                "result_owner_login": {"type": "string"},
                "result_owner_role": {"type": "string", "enum": ["contributor", "project-owner"]},
                "confirmed": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "lenin_owner_project_update",
        "description": "Update a project's name, description or company without changing memberships.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "confirmed"],
            "properties": {
                "project_id": {"type": "string"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "company": {"type": "string"},
                "confirmed": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "lenin_owner_project_result_owner_set",
        "description": "Set or clear the single project member responsible for the result. This does not grant global permissions.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "login", "confirmed"],
            "properties": {
                "project_id": {"type": "string"},
                "login": {"type": "string", "description": "Allocated active user login, or an empty string to clear."},
                "confirmed": {"type": "boolean"},
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
        "name": "lenin_owner_user_password_reset",
        "description": "Reset one user's password, revoke that identity's owner/admin device tokens and return a new one-time temporary password. Existing passwords are never readable.",
        "inputSchema": {
            "type": "object",
            "required": ["login", "confirmed"],
            "properties": {
                "login": {"type": "string"},
                "confirmed": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "lenin_owner_user_context_update",
        "description": "Replace a user's canonical startup context using optimistic locking.",
        "inputSchema": {
            "type": "object",
            "required": ["login", "text", "expected_sha256", "confirmed"],
            "properties": {
                "login": {"type": "string"},
                "text": {"type": "string"},
                "expected_sha256": {"type": "string"},
                "confirmed": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "lenin_owner_project_context_read",
        "description": "Read the shared startup context for one project.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id"],
            "properties": {"project_id": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "lenin_owner_project_context_update",
        "description": "Replace a project's shared startup context using optimistic locking.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "text", "expected_sha256", "confirmed"],
            "properties": {
                "project_id": {"type": "string"},
                "text": {"type": "string"},
                "expected_sha256": {"type": "string"},
                "confirmed": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "lenin_owner_team_chat_read",
        "description": "Read new team-chat messages across all projects or one project using a global sequence cursor. The reason is audited.",
        "inputSchema": {
            "type": "object",
            "required": ["reason"],
            "properties": {
                "reason": {"type": "string"},
                "project_id": {"type": "string"},
                "after_sequence": {"type": "integer", "minimum": 0, "default": 0},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 100},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "lenin_owner_team_chat_post",
        "description": "Publish a plain-text message to one project's team chat as the connected global owner.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "text", "confirmed"],
            "properties": {
                "project_id": {"type": "string"},
                "text": {"type": "string"},
                "confirmed": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "lenin_owner_user_status_set",
        "description": "Enable or disable one user account without changing its role or project grants.",
        "inputSchema": {
            "type": "object",
            "required": ["login", "status", "confirmed"],
            "properties": {
                "login": {"type": "string"},
                "status": {"type": "string", "enum": ["active", "disabled"]},
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
    if name == "lenin_owner_user_list":
        return user_list(args)
    if name == "lenin_owner_user_inspect":
        overview = request("/api/admin/overview")
        return compact_user(find_user(overview, args.get("login")), overview)
    if name == "lenin_owner_user_context_read":
        login, reason = segment(args.get("login"), "login"), required_reason(args)
        return request(f"/api/admin/users/{login}/memory?{urlencode({'reason': reason})}")
    if name == "lenin_owner_user_conversation_read":
        login = segment(args.get("login"), "login")
        project_id = required_text(args.get("project_id"), "project_id")
        reason = required_reason(args)
        limit = bounded_integer(args.get("limit"), 50, 1, 100)
        offset = bounded_integer(args.get("offset"), 0, 0, 50_000)
        query = urlencode({"projectId": project_id, "limit": limit, "offset": offset, "reason": reason})
        return request(f"/api/admin/users/{login}/conversations?{query}")
    if name == "lenin_owner_user_history_read":
        login = segment(args.get("login"), "login")
        query = urlencode({
            "limit": bounded_integer(args.get("limit"), 100, 1, 200),
            "reason": required_reason(args),
        })
        return request(f"/api/admin/users/{login}/history?{query}")
    if name == "lenin_owner_user_uplink_summary":
        return uplink_summary(args)
    if name == "lenin_owner_project_context_read":
        project = required_text(args.get("project_id"), "project_id")
        return request(f"/api/project-context?{urlencode({'projectId': project})}")
    if name == "lenin_owner_team_chat_read":
        query = {
            "reason": required_reason(args),
            "afterSequence": bounded_integer(args.get("after_sequence"), 0, 0, 2_147_483_647),
            "limit": bounded_integer(args.get("limit"), 100, 1, 200),
        }
        if str(args.get("project_id") or "").strip():
            query["projectId"] = required_text(args.get("project_id"), "project_id")
        return request(f"/api/product/owner/team-chat?{urlencode(query)}")
    require_confirmation(args)
    if name == "lenin_owner_user_create":
        return request("/api/admin/users", method="POST", body={
            "id": args.get("login"), "name": args.get("name"), "role": "participant", "projectIds": [],
        })
    if name == "lenin_owner_project_create":
        body = {
            "name": args.get("name"),
            "description": args.get("description", ""),
            "company": args.get("company", ""),
        }
        if str(args.get("result_owner_login") or "").strip():
            body["resultOwnerUserId"] = args.get("result_owner_login")
            body["resultOwnerRole"] = args.get("result_owner_role") or "contributor"
        return request("/api/admin/projects", method="POST", body=body)
    if name == "lenin_owner_project_update":
        project = segment(args.get("project_id"), "project_id")
        body = {key: args[key] for key in ("name", "description", "company") if key in args}
        if not body:
            raise ValueError("Укажите хотя бы одно изменяемое поле проекта.")
        return request(f"/api/admin/projects/{project}", method="PATCH", body=body)
    if name == "lenin_owner_project_result_owner_set":
        project = segment(args.get("project_id"), "project_id")
        return request(f"/api/admin/projects/{project}", method="PATCH", body={
            "resultOwnerUserId": str(args.get("login") or "").strip(),
        })
    if name == "lenin_owner_project_access_set":
        login, project = segment(args.get("login"), "login"), segment(args.get("project_id"), "project_id")
        return request(f"/api/admin/users/{login}/projects/{project}", method="PUT", body={"role": args.get("role")})
    if name == "lenin_owner_project_access_remove":
        login, project = segment(args.get("login"), "login"), segment(args.get("project_id"), "project_id")
        return request(f"/api/admin/users/{login}/projects/{project}", method="DELETE")
    if name == "lenin_owner_user_password_reset":
        login = segment(args.get("login"), "login")
        return request(f"/api/admin/users/{login}/password", method="POST", body={})
    if name == "lenin_owner_user_context_update":
        login = segment(args.get("login"), "login")
        return request(f"/api/admin/users/{login}/memory/context", method="PUT", body={
            "text": args.get("text"),
            "expectedSha256": args.get("expected_sha256"),
        })
    if name == "lenin_owner_project_context_update":
        return request("/api/project-context", method="PUT", body={
            "projectId": required_text(args.get("project_id"), "project_id"),
            "text": args.get("text"),
            "expectedSha256": args.get("expected_sha256"),
        })
    if name == "lenin_owner_team_chat_post":
        return request("/api/product/owner/team-chat", method="POST", body={
            "projectId": required_text(args.get("project_id"), "project_id"),
            "text": required_text(args.get("text"), "text"),
            "confirmed": True,
        })
    if name == "lenin_owner_user_status_set":
        login = segment(args.get("login"), "login")
        return request(f"/api/admin/users/{login}", method="PATCH", body={"status": args.get("status")})
    if name == "lenin_owner_users_bootstrap":
        return bootstrap(args)
    raise ValueError(f"Неизвестный инструмент: {name}")


def require_confirmation(args: dict) -> None:
    if not args.get("confirmed"):
        raise ValueError("Операция меняет доступы: передайте confirmed=true после подтверждения владельца.")


def required_reason(args: dict) -> str:
    reason = str(args.get("reason") or "").strip()
    if not reason:
        raise ValueError("Для чтения приватных данных укажите краткую причину в reason.")
    return reason[:240]


def segment(value: object, name: str) -> str:
    return quote(required_text(value, name), safe="")


def required_text(value: object, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} обязателен")
    return text


def bounded_integer(value: object, fallback: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = fallback
    return max(minimum, min(maximum, parsed))


def find_user(overview: dict, login: object) -> dict:
    target = str(login or "").strip()
    for item in overview.get("users", []):
        if item.get("id") == target:
            return item
    raise ValueError(f"Пользователь {target or 'с пустым login'} не найден.")


def compact_user(user: dict, overview: dict) -> dict:
    projects = {item.get("id"): item for item in overview.get("projects", [])}
    grants = []
    for grant in user.get("projects", []):
        project = projects.get(grant.get("projectId"), {})
        grants.append({
            "project_id": grant.get("projectId"),
            "project_name": project.get("name") or grant.get("projectId"),
            "role": grant.get("role"),
        })
    connection = user.get("uplink") or {}
    return {
        "login": user.get("id"),
        "name": user.get("name"),
        "role": user.get("role"),
        "status": user.get("status"),
        "password_configured": (
            bool(user.get("passwordConfigured"))
            if "passwordConfigured" in user
            else None
        ),
        "access": {
            "all_projects": bool(user.get("allProjects")),
            "effective_project_count": user.get("effectiveProjectCount", 0),
            "grants": grants,
        },
        "uplink": {
            "state": connection.get("state", "unavailable"),
            "client_count": connection.get("clientCount", 0),
            "last_sync_at": connection.get("lastSyncAt"),
            "versions": connection.get("versions", []),
        },
    }


def user_list(args: dict) -> dict:
    overview = request("/api/admin/overview")
    query = str(args.get("query") or "").strip().casefold()
    project_id = str(args.get("project_id") or "").strip()
    result = []
    for user in overview.get("users", []):
        if query and query not in f"{user.get('id', '')} {user.get('name', '')}".casefold():
            continue
        if args.get("role") and user.get("role") != args["role"]:
            continue
        if args.get("status") and user.get("status") != args["status"]:
            continue
        if args.get("uplink_state") and (user.get("uplink") or {}).get("state") != args["uplink_state"]:
            continue
        project_ids = {grant.get("projectId") for grant in user.get("projects", [])}
        if project_id and not user.get("allProjects") and project_id not in project_ids:
            continue
        result.append(compact_user(user, overview))
    result.sort(key=lambda item: (item["name"] or item["login"] or "").casefold())
    return {"count": len(result), "users": result}


def uplink_summary(args: dict) -> dict:
    login, reason = segment(args.get("login"), "login"), required_reason(args)
    query = urlencode({"reason": reason})
    try:
        return request(f"/api/admin/users/{login}/uplink?{query}")
    except ValueError as error:
        if "endpoint not found" not in str(error).lower():
            raise
        memory = request(f"/api/admin/users/{login}/memory?{query}")
        return {"user": memory.get("user"), "uplink": memory.get("uplink")}


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
                    "serverInfo": {"name": "lenin-owner", "version": "0.4.0"},
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
