"""Offline stub: gold NL samples + conservative fallback."""

from __future__ import annotations

from typing import Any


def stub_compile(nl_text: str, req_id: str) -> dict[str, Any]:
    text = nl_text.strip()
    if "账号已冻结" in text:
        return _frozen(req_id)
    if "手机号或密码错误" in text or ("错误密码" in text and "登录" in text):
        return _wrong_password(req_id)
    if "已登录" in text and ("主站" in text or "main.z-niu.com" in text):
        return _after_login(req_id)
    if "清洗次数下拉" in text or ("三次及以上" in text and "人工待清洗" in text):
        return _mg0473_options(req_id)
    return {
        "case_id": f"TC_{req_id}_NEEDS_REVIEW",
        "title": "编译不确定，需人工补全",
        "requirement_id": req_id,
        "tags": ["compiled", "stub"],
        "meta": {
            "needs_review": True,
            "compile_backend": "stub",
            "review_notes": "无匹配的离线样例，且未配置 LLM Key；请补 Key 或改 NL",
        },
        "steps": [
            {
                "action": "open",
                "url": "https://login.z-niu.com/",
                "description": "占位打开（需人工修改）",
            }
        ],
    }


def _after_login(req_id: str) -> dict[str, Any]:
    return {
        "case_id": "TC_DEMO_AFTER_LOGIN_001",
        "title": "已登录访问业务主站",
        "requirement_id": req_id,
        "base_url": "https://main.z-niu.com/",
        "tags": ["compiled", "stub"],
        "meta": {"needs_review": False, "compile_backend": "stub"},
        "preconditions": [{"auth": "logged_in", "account_ref": "default_tester"}],
        "defaults": {"on_action": {"observe": {"window_ms": 10000}}},
        "steps": [
            {
                "action": "open",
                "url": "https://main.z-niu.com/",
                "description": "打开业务主站",
            },
            {
                "action": "assert_url_contains",
                "expect": "main.z-niu.com",
                "description": "断言已在业务主站",
            },
        ],
    }


def _wrong_password(req_id: str) -> dict[str, Any]:
    return {
        "case_id": "TC_TOAST_WRONG_PASSWORD",
        "title": "错误密码应出现失败 toast",
        "requirement_id": req_id,
        "base_url": "https://login.z-niu.com/",
        "tags": ["compiled", "stub", "toast"],
        "meta": {"needs_review": False, "compile_backend": "stub"},
        "steps": [
            {
                "action": "open",
                "url": "https://login.z-niu.com/",
                "description": "打开登录页",
                "observe": {"forbid_toast_levels": []},
            },
            {
                "action": "fill",
                "element": "用户名输入框",
                "value": "16676583008",
                "description": "输入手机号",
            },
            {
                "action": "wait_visible",
                "element": "组织下拉",
                "timeout_ms": 10000,
                "description": "等待组织下拉出现",
            },
            {
                "action": "select",
                "element": "组织下拉",
                "value": "墨斗科技 / 总部",
                "description": "选择组织",
            },
            {
                "action": "fill",
                "element": "密码输入框",
                "value": "wrong-password",
                "description": "输入错误密码",
            },
            {
                "action": "click",
                "element": "登录按钮",
                "description": "点击登录",
                "observe": {
                    "window_ms": 8000,
                    "forbid_toast_levels": [],
                    "toasts": [{"expect": "error", "contains": "手机号或密码错误"}],
                },
            },
        ],
    }


def _frozen(req_id: str) -> dict[str, Any]:
    return {
        "case_id": "TC_TOAST_FROZEN_ORG",
        "title": "默认组织账号冻结应出现失败 toast",
        "requirement_id": req_id,
        "base_url": "https://login.z-niu.com/",
        "tags": ["compiled", "stub", "toast"],
        "meta": {"needs_review": False, "compile_backend": "stub"},
        "steps": [
            {
                "action": "open",
                "url": "https://login.z-niu.com/",
                "description": "打开登录页",
                "observe": {"forbid_toast_levels": []},
            },
            {
                "action": "fill",
                "element": "用户名输入框",
                "value": "16676583008",
                "description": "输入手机号，不改组织",
            },
            {
                "action": "wait_visible",
                "element": "组织下拉",
                "timeout_ms": 10000,
                "description": "等待组织下拉",
            },
            {
                "action": "fill",
                "element": "密码输入框",
                "value": "wrong-password",
                "description": "输入密码",
            },
            {
                "action": "click",
                "element": "登录按钮",
                "description": "点击登录",
                "observe": {
                    "window_ms": 8000,
                    "forbid_toast_levels": [],
                    "toasts": [{"expect": "error", "contains": "账号已冻结，请先联系管理员"}],
                },
            },
        ],
    }


def _mg0473_options(req_id: str) -> dict[str, Any]:
    return {
        "case_id": "TC-MG0473-001",
        "title": "人工待清洗-清洗次数下拉五项且三次与三次及以上独立",
        "requirement_id": req_id,
        "base_url": "https://lead.z-niu.com",
        "tags": ["compiled", "stub", "MG0473"],
        "meta": {"needs_review": False, "compile_backend": "stub"},
        "preconditions": [{"auth": "logged_in", "account_ref": "default_tester"}],
        "defaults": {
            "on_action": {"observe": {"window_ms": 8000, "forbid_toast_levels": ["error"]}}
        },
        "steps": [
            {"action": "open", "url": "https://lead.z-niu.com/pool/clean", "description": "打开清洗池"},
            {"action": "wait_visible", "element": "人工待清洗"},
            {"action": "click", "element": "人工待清洗", "description": "进入人工待清洗"},
            {"action": "click_if_visible", "element": "展开筛选"},
            {"action": "click_if_visible", "element": "全部"},
            {"action": "click_if_visible", "element": "重置"},
            {"action": "wait_visible", "element": "查询"},
            {
                "action": "assert_options",
                "element": "清洗次数",
                "expect": "未清洗,首次清洗,二次清洗,三次清洗,三次及以上",
            },
        ],
    }
