from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import logging
from re import sub
from uuid import uuid4

from jsonpath import jsonpath

from settings import settings
from util.assert_util import assert_response
from util.request_util import RequestUtil

logger = logging.getLogger(__name__)


@dataclass
class ApiResource:
    token: str
    resource_id: int | None = None


@dataclass
class OrderScenario:
    token: str
    order_id: int
    refund_id: int | None = None
    user_token: str | None = None


def api_url(path: str) -> str:
    return f"{settings.api_base_url.rstrip('/')}/{path.lstrip('/')}"


def response_json(response):
    """Fixture setup must succeed at both HTTP and business-code levels."""
    return assert_response(response, {"code": 0})


def response_value(response, path: str):
    values = jsonpath(response_json(response), path)
    if not values:
        raise AssertionError(f"响应缺少字段 {path}: {response.text[:300]}")
    return values[0]


def create_category(
    client: RequestUtil, token: str, *, parent_id: int = 1
) -> ApiResource:
    name = f"自动化测试分类-{uuid4().hex[:10]}"
    response = client.send_all_request(
        method="POST",
        url=api_url("/api/admin/categories"),
        json={"name": name, "parentId": parent_id, "sort": 0},
        token=token,
    )
    return ApiResource(token, int(response_value(response, "$..categoryId")))


def create_product(
    client: RequestUtil, token: str, *, category_id: int = 12
) -> ApiResource:
    name = f"自动化测试商品-{uuid4().hex[:10]}"
    response = client.send_all_request(
        method="POST",
        url=api_url("/api/admin/products"),
        json={
            "categoryId": category_id,
            "name": name,
            "description": "fixture-created product",
            "price": 1.00,
            "mainImageUrl": "https://example.test/fixture-main.jpg",
        },
        token=token,
    )
    return ApiResource(token, int(response_value(response, "$..productId")))


def replace_path_id(request: dict, old_id: int, new_id: int) -> dict:
    """Copy a YAML request and replace only a path segment, never its payload."""
    result = deepcopy(request)
    result["url"] = sub(rf"/{old_id}(?=/|$)", f"/{new_id}", result["url"])
    return result


def delete_resource(client: RequestUtil, method: str, path: str, token: str) -> None:
    response = client.send_all_request(method=method, url=api_url(path), token=token)
    if response.status_code not in (200, 204, 404):
        logger.warning(
            "fixture cleanup failed: %s %s -> %s", method, path, response.status_code
        )
    elif response.status_code == 200:
        body = response.json()
        if body.get("code") != 0:
            logger.warning(
                "fixture cleanup failed: %s %s -> code %s",
                method,
                path,
                body.get("code"),
            )
