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
        "description": "List Lenin companies, projects, users and current grants. Global owner access only.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "lenin_owner_company_list",
        "description": "Return a compact filterable company directory with member and project counts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "status": {"type": "string", "enum": ["active", "archived"]},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "lenin_owner_company_inspect",
        "description": "Inspect one company, its explicit members and its independent projects.",
        "inputSchema": {
            "type": "object",
            "required": ["company_id"],
            "properties": {"company_id": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "lenin_owner_project_list",
        "description": "Return a compact filterable project directory, optionally limited to one company.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "company_id": {"type": "string"},
                "status": {"type": "string", "enum": ["active", "archived"]},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "lenin_owner_project_inspect",
        "description": "Inspect one project, its company, responsible person and effective participants.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id"],
            "properties": {"project_id": {"type": "string"}},
            "additionalProperties": False,
        },
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
        "name": "lenin_owner_company_create",
        "description": "Create a company and optionally appoint one active non-guest user as company owner.",
        "inputSchema": {
            "type": "object",
            "required": ["name", "confirmed"],
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "owner_login": {"type": "string"},
                "confirmed": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "lenin_owner_company_update",
        "description": "Update a company's name, description or lifecycle status.",
        "inputSchema": {
            "type": "object",
            "required": ["company_id", "confirmed"],
            "properties": {
                "company_id": {"type": "string"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "status": {"type": "string", "enum": ["active", "archived"]},
                "confirmed": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "lenin_owner_company_member_set",
        "description": "Add a user to one company or update that existing company role.",
        "inputSchema": {
            "type": "object",
            "required": ["company_id", "login", "role", "confirmed"],
            "properties": {
                "company_id": {"type": "string"},
                "login": {"type": "string"},
                "role": {"type": "string", "enum": ["company-member", "company-owner"]},
                "confirmed": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "lenin_owner_company_member_remove",
        "description": "Remove a user from one company and its projects after owner confirmation.",
        "inputSchema": {
            "type": "object",
            "required": ["company_id", "login", "confirmed"],
            "properties": {
                "company_id": {"type": "string"},
                "login": {"type": "string"},
                "confirmed": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "lenin_owner_company_invite_create",
        "description": "Create a time-limited company invitation and return its one-time code.",
        "inputSchema": {
            "type": "object",
            "required": ["company_id", "role", "confirmed"],
            "properties": {
                "company_id": {"type": "string"},
                "role": {"type": "string", "enum": ["company-member", "company-owner"]},
                "ttl_ms": {"type": "integer", "minimum": 300000, "maximum": 2592000000},
                "confirmed": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "lenin_owner_project_create",
        "description": "Create an independent root or child project and optionally allocate one active user as the person responsible for its result.",
        "inputSchema": {
            "type": "object",
            "required": ["name", "confirmed"],
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "company_id": {"type": "string", "description": "Company id. A child project inherits its parent's company when omitted."},
                "parent_project_id": {"type": "string", "description": "Parent project id. Omit for a root project."},
                "inherit_members": {"type": "boolean", "default": True},
                "inherit_materials": {"type": "boolean", "default": True},
                "result_owner_login": {"type": "string"},
                "result_owner_role": {"type": "string", "enum": ["contributor", "project-owner"]},
                "confirmed": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "lenin_owner_project_update",
        "description": "Update a project's identity, company, parent or downward inheritance switches without changing direct memberships.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "confirmed"],
            "properties": {
                "project_id": {"type": "string"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "company_id": {"type": "string"},
                "parent_project_id": {"type": "string", "description": "Parent project id, or an empty string to make the project a root."},
                "inherit_members": {"type": "boolean"},
                "inherit_materials": {"type": "boolean"},
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
    if name == "lenin_owner_company_list":
        return company_list(args)
    if name == "lenin_owner_company_inspect":
        return company_inspect(args)
    if name == "lenin_owner_project_list":
        return project_list(args)
    if name == "lenin_owner_project_inspect":
        return project_inspect(args)
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
    if name == "lenin_owner_company_create":
        body = {
            "name": required_text(args.get("name"), "name"),
            "description": str(args.get("description") or "").strip(),
        }
        if str(args.get("owner_login") or "").strip():
            body["ownerUserId"] = required_text(args.get("owner_login"), "owner_login")
        return request("/api/admin/companies", method="POST", body=body)
    if name == "lenin_owner_company_update":
        company = segment(args.get("company_id"), "company_id")
        body = {key: args[key] for key in ("name", "description", "status") if key in args}
        if not body:
            raise ValueError("Укажите хотя бы одно изменяемое поле компании.")
        return request(f"/api/admin/companies/{company}", method="PATCH", body=body)
    if name == "lenin_owner_company_member_set":
        company_id = required_text(args.get("company_id"), "company_id")
        login = required_text(args.get("login"), "login")
        overview = request("/api/admin/overview")
        user = find_user(overview, login)
        existing = any(
            item.get("companyId") == company_id
            for item in user.get("companies", [])
        )
        return request("/api/product/owner/company-members", method="PATCH" if existing else "POST", body={
            "companyId": company_id,
            "userId": login,
            "role": args.get("role"),
        })
    if name == "lenin_owner_company_member_remove":
        query = urlencode({
            "companyId": required_text(args.get("company_id"), "company_id"),
            "userId": required_text(args.get("login"), "login"),
        })
        return request(f"/api/product/owner/company-members?{query}", method="DELETE")
    if name == "lenin_owner_company_invite_create":
        company = segment(args.get("company_id"), "company_id")
        body = {"role": args.get("role")}
        if "ttl_ms" in args:
            body["ttlMs"] = bounded_integer(args.get("ttl_ms"), 604_800_000, 300_000, 2_592_000_000)
        return request(f"/api/admin/companies/{company}/invites", method="POST", body=body)
    if name == "lenin_owner_project_create":
        body = {
            "name": args.get("name"),
            "description": args.get("description", ""),
        }
        for source, target in (
            ("company_id", "companyId"),
            ("parent_project_id", "parentProjectId"),
            ("inherit_members", "inheritMembers"),
            ("inherit_materials", "inheritMaterials"),
        ):
            if source in args:
                body[target] = args[source]
        if str(args.get("result_owner_login") or "").strip():
            body["resultOwnerUserId"] = args.get("result_owner_login")
            body["resultOwnerRole"] = args.get("result_owner_role") or "contributor"
        return request("/api/admin/projects", method="POST", body=body)
    if name == "lenin_owner_project_update":
        project = segment(args.get("project_id"), "project_id")
        body = {key: args[key] for key in ("name", "description") if key in args}
        for source, target in (
            ("company_id", "companyId"),
            ("parent_project_id", "parentProjectId"),
            ("inherit_members", "inheritMembers"),
            ("inherit_materials", "inheritMaterials"),
        ):
            if source in args:
                body[target] = args[source]
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
    for grant in user.get("effectiveProjects") or user.get("projects", []):
        project = projects.get(grant.get("projectId"), {})
        grants.append({
            "project_id": grant.get("projectId"),
            "project_name": project.get("name") or grant.get("projectId"),
            "role": grant.get("role"),
            "access_source": grant.get("accessSource") or "membership",
            "inherited_from_project_id": grant.get("inheritedFromProjectId") or "",
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


def compact_company(company: dict) -> dict:
    return {
        "company_id": company.get("id"),
        "name": company.get("name"),
        "description": company.get("description") or "",
        "status": company.get("status"),
        "member_count": company.get("memberCount", 0),
        "project_count": company.get("projectCount", 0),
    }


def compact_project(project: dict) -> dict:
    return {
        "project_id": project.get("id"),
        "name": project.get("name"),
        "description": project.get("description") or "",
        "status": project.get("status"),
        "company_id": project.get("companyId") or "",
        "company_name": project.get("companyName") or "",
        "parent_project_id": project.get("parentProjectId") or "",
        "inherit_members": bool(project.get("inheritMembers", True)),
        "inherit_materials": bool(project.get("inheritMaterials", True)),
        "result_owner_login": project.get("resultOwnerUserId") or "",
        "result_owner_name": project.get("resultOwnerName") or "",
        "member_count": project.get("memberCount", 0),
        "publication_status": project.get("publicationStatus") or "",
        "public_url": project.get("publicUrl") or "",
    }


def find_company(overview: dict, company_id: object) -> dict:
    target = str(company_id or "").strip()
    for item in overview.get("companies", []):
        if item.get("id") == target:
            return item
    raise ValueError(f"Компания {target or 'с пустым company_id'} не найдена.")


def find_project(overview: dict, project_id: object) -> dict:
    target = str(project_id or "").strip()
    for item in overview.get("projects", []):
        if item.get("id") == target:
            return item
    raise ValueError(f"Проект {target or 'с пустым project_id'} не найден.")


def company_list(args: dict) -> dict:
    overview = request("/api/admin/overview")
    query = str(args.get("query") or "").strip().casefold()
    companies = []
    for company in overview.get("companies", []):
        if query and query not in f"{company.get('id', '')} {company.get('name', '')}".casefold():
            continue
        if args.get("status") and company.get("status") != args["status"]:
            continue
        companies.append(compact_company(company))
    companies.sort(key=lambda item: (item["name"] or item["company_id"] or "").casefold())
    return {"count": len(companies), "companies": companies}


def company_inspect(args: dict) -> dict:
    overview = request("/api/admin/overview")
    company = find_company(overview, args.get("company_id"))
    company_id = company.get("id")
    members = []
    for user in overview.get("users", []):
        membership = next(
            (item for item in user.get("companies", []) if item.get("companyId") == company_id),
            None,
        )
        if membership:
            members.append({
                "login": user.get("id"),
                "name": user.get("name"),
                "status": user.get("status"),
                "role": membership.get("role"),
            })
    members.sort(key=lambda item: (item["name"] or item["login"] or "").casefold())
    projects = [
        compact_project(project)
        for project in overview.get("projects", [])
        if project.get("companyId") == company_id
    ]
    projects.sort(key=lambda item: (item["name"] or item["project_id"] or "").casefold())
    return {"company": compact_company(company), "members": members, "projects": projects}


def project_list(args: dict) -> dict:
    overview = request("/api/admin/overview")
    query = str(args.get("query") or "").strip().casefold()
    company_id = str(args.get("company_id") or "").strip()
    projects = []
    for project in overview.get("projects", []):
        if query and query not in f"{project.get('id', '')} {project.get('name', '')}".casefold():
            continue
        if company_id and project.get("companyId") != company_id:
            continue
        if args.get("status") and project.get("status") != args["status"]:
            continue
        projects.append(compact_project(project))
    projects.sort(key=lambda item: (item["company_name"], item["name"] or item["project_id"] or ""))
    return {"count": len(projects), "projects": projects}


def project_inspect(args: dict) -> dict:
    overview = request("/api/admin/overview")
    project = find_project(overview, args.get("project_id"))
    project_id = project.get("id")
    participants = []
    for user in overview.get("users", []):
        grant = next(
            (
                item
                for item in user.get("effectiveProjects") or user.get("projects", [])
                if item.get("projectId") == project_id
            ),
            None,
        )
        if not grant and not user.get("allProjects"):
            continue
        participants.append({
            "login": user.get("id"),
            "name": user.get("name"),
            "status": user.get("status"),
            "role": grant.get("role") if grant else user.get("role"),
            "access_source": grant.get("accessSource") if grant else "global-role",
        })
    participants.sort(key=lambda item: (item["name"] or item["login"] or "").casefold())
    return {"project": compact_project(project), "participants": participants}


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
        project_ids = {
            grant.get("projectId")
            for grant in user.get("effectiveProjects") or user.get("projects", [])
        }
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
                    "serverInfo": {"name": "lenin-owner", "version": "0.6.1"},
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
