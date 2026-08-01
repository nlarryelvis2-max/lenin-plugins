#!/usr/bin/env python3
"""Dependency-free stdio MCP for Lenin owner accounts."""
from __future__ import annotations

import json
import os
import re
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
        "name": "lenin_owner_capabilities",
        "description": "Check the live platform owner API version, feature support and recommended Owner MCP version.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "lenin_owner_portfolio_digest",
        "description": "Read an evidence-backed portfolio digest with companies, projects, accountable people, tasks, heartbeat receipts, new team messages and typed attention items.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "after_sequence": {"type": "integer", "minimum": 0, "default": 0},
                "include_archived": {"type": "boolean", "default": False},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 200},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "lenin_owner_activity_digest",
        "description": "Use for 'today', 'recently', 'what moved' and 'who wrote what': read recent team messages across projects plus current project events and attention, grouped by project and author. The reason is audited.",
        "inputSchema": {
            "type": "object",
            "required": ["reason"],
            "properties": {
                "reason": {"type": "string", "description": "Short operational reason for reviewing shared team activity."},
                "since_hours": {"type": "integer", "minimum": 1, "maximum": 168, "default": 24},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 200},
            },
            "additionalProperties": False,
        },
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
        "name": "lenin_owner_project_digest",
        "description": "Read one complete project-visible digest: documents, history, shared materials, commitments, clarifications, autopilot receipts, integrations and new team messages.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id"],
            "properties": {
                "project_id": {"type": "string"},
                "after_sequence": {"type": "integer", "minimum": 0, "default": 0},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "lenin_owner_project_documents_list",
        "description": "List the five canonical project documents with update time and a bounded excerpt.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id"],
            "properties": {"project_id": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "lenin_owner_project_document_read",
        "description": "Read one canonical shared project document in full.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "document"],
            "properties": {
                "project_id": {"type": "string"},
                "document": {
                    "type": "string",
                    "enum": ["brief", "context", "roadmap", "decisions", "chronicle"],
                },
            },
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
        "description": "Create a company. The platform appoints the connected owner by default, or owner_login when provided. Use lenin_owner_company_project_create when the request also includes a first project.",
        "inputSchema": {
            "type": "object",
            "required": ["name", "confirmed"],
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "icon": {"type": "string", "description": "Optional short emoji or icon, up to 8 Unicode characters."},
                "owner_login": {"type": "string"},
                "confirmed": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "lenin_owner_company_project_create",
        "description": "Preferred single workflow for a new company with its first project: appoint an active non-guest company owner, create the company, then attach the project using the exact company id returned by the platform.",
        "inputSchema": {
            "type": "object",
            "required": ["company_name", "owner_login", "project_name", "confirmed"],
            "properties": {
                "company_name": {"type": "string"},
                "company_description": {"type": "string"},
                "company_icon": {"type": "string", "description": "Optional short emoji or icon, up to 8 Unicode characters."},
                "owner_login": {"type": "string"},
                "project_name": {"type": "string"},
                "project_description": {"type": "string"},
                "project_icon": {"type": "string", "description": "Optional short emoji or icon, up to 8 Unicode characters."},
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
                "icon": {"type": "string", "description": "Optional short emoji or icon, up to 8 Unicode characters."},
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
        "description": "Create an independent root or child project. It starts without a result owner unless result_owner_login is explicitly provided.",
        "inputSchema": {
            "type": "object",
            "required": ["name", "confirmed"],
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "icon": {"type": "string", "description": "Optional short emoji or icon, up to 8 Unicode characters."},
                "company_id": {"type": "string", "description": "Company id. A child project inherits its parent's company when omitted."},
                "parent_project_id": {"type": "string", "description": "Parent project id. Omit for a root project."},
                "inherit_members": {"type": "boolean", "default": True},
                "inherit_materials": {"type": "boolean", "default": True},
                "result_owner_login": {
                    "type": "string",
                    "description": "Optional active participant login. Omit to leave result responsibility unassigned.",
                },
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
                "icon": {"type": "string", "description": "Optional short emoji or icon, up to 8 Unicode characters."},
                "status": {"type": "string", "enum": ["active", "archived"]},
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
        "name": "lenin_owner_project_archive",
        "description": "Archive one project after confirmation. Active subprojects must be archived first.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "confirmed"],
            "properties": {
                "project_id": {"type": "string"},
                "confirmed": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "lenin_owner_project_restore",
        "description": "Restore one archived project after confirmation. Its company and parent chain must already be active.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "confirmed"],
            "properties": {
                "project_id": {"type": "string"},
                "confirmed": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "lenin_owner_project_invite_create",
        "description": "Create a time-limited invitation for an existing or new participant and return its one-time code.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "role", "user_role", "confirmed"],
            "properties": {
                "project_id": {"type": "string"},
                "role": {"type": "string", "enum": ["viewer", "contributor", "project-owner"]},
                "user_role": {"type": "string", "enum": ["participant", "guest"]},
                "ttl_ms": {"type": "integer", "minimum": 300000, "maximum": 2592000000},
                "confirmed": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "lenin_owner_project_guest_link_create",
        "description": "Create a dedicated guest profile and one-time magic project link for an external participant.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "name", "job_title", "confirmed"],
            "properties": {
                "project_id": {"type": "string"},
                "name": {"type": "string"},
                "job_title": {"type": "string"},
                "confirmed": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "lenin_owner_project_delegate",
        "description": "Publish a durable owner instruction and run the normal Lenin agent inside exactly one project with its existing Project MCP, materials, memory and delivery verification.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "instruction", "operation_id", "confirmed"],
            "properties": {
                "project_id": {"type": "string"},
                "instruction": {"type": "string", "minLength": 3, "maxLength": 20000},
                "operation_id": {
                    "type": "string",
                    "pattern": "^[A-Za-z0-9_-]{8,128}$",
                    "description": "Stable id for retries. Reuse the same value for the same logical instruction.",
                },
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
        "name": "lenin_owner_message_prepare",
        "description": "Prepare, but do not send, one exact project team-chat message. Select owner or Lenin as the visible sender and the whole team or one participant as target. Always show the returned complete preview to the owner: sender, recipient, project, team-visible delivery and exact text.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "sender", "target", "text"],
            "properties": {
                "project_id": {"type": "string"},
                "sender": {
                    "type": "string",
                    "enum": ["owner", "lenin"],
                    "description": "Visible author. owner = connected owner; lenin = Lenin label with owner-authored exact text.",
                },
                "target": {
                    "type": "string",
                    "enum": ["team", "participant"],
                    "description": "participant is an addressed @mention in the selected project team chat, not a private DM.",
                },
                "recipient_login": {
                    "type": "string",
                    "description": "Required only for target=participant; must be an active participant of this project.",
                },
                "text": {"type": "string", "minLength": 1, "maxLength": 4000},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "lenin_owner_message_send",
        "description": "Send exactly one previously prepared message using only its one-time confirmation token. Call this only after the owner explicitly confirms the complete preview; never infer confirmation or accept changed sender, target, project or text.",
        "inputSchema": {
            "type": "object",
            "required": ["confirmation_token"],
            "properties": {
                "confirmation_token": {
                    "type": "string",
                    "pattern": "^lom_[A-Za-z0-9_-]{32,128}$",
                    "description": "Short-lived token returned by lenin_owner_message_prepare.",
                },
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
        "name": "lenin_owner_user_archive",
        "description": "Archive (disable) one user account without deleting its history or grants.",
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
        "name": "lenin_owner_user_restore",
        "description": "Restore one disabled user account without changing its role or project grants.",
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
    if name == "lenin_owner_capabilities":
        return request("/api/product/owner/capabilities")
    if name == "lenin_owner_portfolio_digest":
        query = urlencode({
            "afterSequence": bounded_integer(args.get("after_sequence"), 0, 0, 2_147_483_647),
            "includeArchived": "true" if args.get("include_archived") else "false",
            "limit": bounded_integer(args.get("limit"), 200, 1, 200),
        })
        return request(f"/api/product/owner/portfolio-digest?{query}")
    if name == "lenin_owner_activity_digest":
        query = urlencode({
            "reason": required_reason(args),
            "sinceHours": bounded_integer(args.get("since_hours"), 24, 1, 168),
            "limit": bounded_integer(args.get("limit"), 200, 1, 200),
        })
        return request(f"/api/product/owner/activity-digest?{query}")
    if name == "lenin_owner_company_list":
        return company_list(args)
    if name == "lenin_owner_company_inspect":
        return company_inspect(args)
    if name == "lenin_owner_project_list":
        return project_list(args)
    if name == "lenin_owner_project_inspect":
        return project_inspect(args)
    if name == "lenin_owner_project_digest":
        project = segment(args.get("project_id"), "project_id")
        query = urlencode({
            "afterSequence": bounded_integer(args.get("after_sequence"), 0, 0, 2_147_483_647),
        })
        return request(f"/api/product/owner/projects/{project}/digest?{query}")
    if name == "lenin_owner_project_documents_list":
        project = segment(args.get("project_id"), "project_id")
        return request(f"/api/product/owner/projects/{project}/documents")
    if name == "lenin_owner_project_document_read":
        project = segment(args.get("project_id"), "project_id")
        document = segment(args.get("document"), "document")
        return request(f"/api/product/owner/projects/{project}/documents/{document}")
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
    if name == "lenin_owner_message_prepare":
        target = required_text(args.get("target"), "target")
        recipient = str(args.get("recipient_login") or "").strip()
        if target == "participant" and not recipient:
            raise ValueError("Для target=participant укажите recipient_login.")
        if target == "team" and recipient:
            raise ValueError("Для target=team не передавайте recipient_login.")
        return request("/api/product/owner/messages/preview", method="POST", body={
            "projectId": required_text(args.get("project_id"), "project_id"),
            "sender": required_text(args.get("sender"), "sender"),
            "target": target,
            "recipientUserId": recipient,
            "text": required_text(args.get("text"), "text"),
        })
    if name == "lenin_owner_message_send":
        return request("/api/product/owner/messages/send", method="POST", body={
            "confirmationToken": required_text(args.get("confirmation_token"), "confirmation_token"),
        })
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
        if "icon" in args:
            body["icon"] = str(args.get("icon") or "").strip()
        if str(args.get("owner_login") or "").strip():
            body["ownerUserId"] = required_text(args.get("owner_login"), "owner_login")
        return request("/api/admin/companies", method="POST", body=body)
    if name == "lenin_owner_company_project_create":
        company_body = {
            "name": required_text(args.get("company_name"), "company_name"),
            "description": str(args.get("company_description") or "").strip(),
            "ownerUserId": required_text(args.get("owner_login"), "owner_login"),
        }
        if "company_icon" in args:
            company_body["icon"] = str(args.get("company_icon") or "").strip()
        created = request("/api/admin/companies", method="POST", body=company_body)
        company = created.get("company") or {}
        company_id = required_text(company.get("id"), "returned company id")
        project_body = {
            "name": required_text(args.get("project_name"), "project_name"),
            "description": str(args.get("project_description") or "").strip(),
            "companyId": company_id,
        }
        if "project_icon" in args:
            project_body["icon"] = str(args.get("project_icon") or "").strip()
        try:
            project = request("/api/admin/projects", method="POST", body=project_body)
        except ValueError as error:
            rollback = "failed"
            try:
                request(f"/api/admin/companies/{segment(company_id, 'company_id')}", method="PATCH", body={
                    "status": "archived",
                })
                rollback = "archived"
            except ValueError:
                pass
            raise ValueError(
                f"Проект не создан; созданная компания {rollback}. Проверьте каталог компаний перед повтором: {error}"
            ) from error
        return {"company": company, "project": project.get("project") or project}
    if name == "lenin_owner_company_update":
        company = segment(args.get("company_id"), "company_id")
        body = {key: args[key] for key in ("name", "description", "icon", "status") if key in args}
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
        if "icon" in args:
            body["icon"] = str(args.get("icon") or "").strip()
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
        body = {key: args[key] for key in ("name", "description", "icon", "status") if key in args}
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
    if name in {"lenin_owner_project_archive", "lenin_owner_project_restore"}:
        project = segment(args.get("project_id"), "project_id")
        status = "archived" if name.endswith("_archive") else "active"
        return request(f"/api/admin/projects/{project}", method="PATCH", body={"status": status})
    if name == "lenin_owner_project_invite_create":
        project = segment(args.get("project_id"), "project_id")
        body = {
            "role": args.get("role"),
            "userRole": args.get("user_role"),
        }
        if "ttl_ms" in args:
            body["ttlMs"] = bounded_integer(args.get("ttl_ms"), 604_800_000, 300_000, 2_592_000_000)
        return request(f"/api/admin/projects/{project}/invites", method="POST", body=body)
    if name == "lenin_owner_project_guest_link_create":
        project = segment(args.get("project_id"), "project_id")
        return request(f"/api/admin/projects/{project}/guest-links", method="POST", body={
            "name": required_text(args.get("name"), "name"),
            "jobTitle": required_text(args.get("job_title"), "job_title"),
        })
    if name == "lenin_owner_project_delegate":
        project = segment(args.get("project_id"), "project_id")
        return request(f"/api/product/owner/projects/{project}/delegate", method="POST", body={
            "instruction": required_text(args.get("instruction"), "instruction"),
            "operationId": required_operation_id(args),
            "confirmed": True,
        })
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
    if name == "lenin_owner_user_status_set":
        login = segment(args.get("login"), "login")
        return request(f"/api/admin/users/{login}", method="PATCH", body={"status": args.get("status")})
    if name in {"lenin_owner_user_archive", "lenin_owner_user_restore"}:
        login = segment(args.get("login"), "login")
        status = "disabled" if name.endswith("_archive") else "active"
        return request(f"/api/admin/users/{login}", method="PATCH", body={"status": status})
    if name == "lenin_owner_users_bootstrap":
        return bootstrap(args)
    raise ValueError(f"Неизвестный инструмент: {name}")


def require_confirmation(args: dict) -> None:
    if not args.get("confirmed"):
        raise ValueError("Операция меняет общие данные: передайте confirmed=true после подтверждения владельца.")


def required_reason(args: dict) -> str:
    reason = str(args.get("reason") or "").strip()
    if not reason:
        raise ValueError("Для чтения приватных данных укажите краткую причину в reason.")
    return reason[:240]


def required_operation_id(args: dict) -> str:
    operation_id = str(args.get("operation_id") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", operation_id):
        raise ValueError("operation_id должен содержать 8–128 латинских букв, цифр, '_' или '-'.")
    return operation_id


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
        "icon": company.get("icon") or "",
        "status": company.get("status"),
        "member_count": company.get("memberCount", 0),
        "project_count": company.get("projectCount", 0),
    }


def compact_project(project: dict) -> dict:
    return {
        "project_id": project.get("id"),
        "name": project.get("name"),
        "description": project.get("description") or "",
        "icon": project.get("icon") or "",
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
        "telegram": project.get("telegram") or {},
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
                    "serverInfo": {"name": "lenin-owner", "version": "0.9.1"},
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
